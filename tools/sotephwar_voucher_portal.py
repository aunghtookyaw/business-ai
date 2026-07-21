"""SotePhwar Voucher routes mounted in the local BigShot Business OS service."""
import logging
import tempfile
from pathlib import Path

from flask import jsonify, request, send_file, url_for

from tools import sotephwar_voucher_repository, voucher_engine
from tools.sotephwar_voucher_pdf import write_sotephwar_voucher_pdf


LOGGER = logging.getLogger(__name__)


def _history_request_args(args):
    """Normalize optional history filters without touching voucher validation."""
    page = (args.get("page") or "1").strip()
    page_size = (args.get("page_size") or "20").strip()
    status = (args.get("status") or args.get("payment_status") or "all").strip() or "all"
    customer = (args.get("customer") or "").strip()
    voucher = (args.get("voucher") or args.get("voucher_number") or "").strip()
    start_date = (args.get("start_date") or args.get("date_from") or "").strip() or None
    end_date = (args.get("end_date") or args.get("date_to") or "").strip() or None
    filters = {
        "customer": customer,
        "voucher_number": voucher,
        "date_from": start_date,
        "date_to": end_date,
        "payment_status": "" if status.lower() == "all" else status,
    }
    return filters, page, page_size


def _validation_code(errors):
    message = str((errors or [""])[0]).lower()
    rules = (
        ("voucher_number is required", "voucher_number_required"),
        ("customer is required", "customer_required"),
        ("voucher_date must use", "voucher_date_invalid"),
        ("product_code is invalid", "product_code_invalid"),
        ("quantity must be a whole number", "quantity_not_whole_bottles"),
        ("quantity must be greater than zero", "quantity_not_positive"),
        ("unit_price cannot be negative", "unit_price_negative"),
        ("total must be a whole mmk amount", "line_total_not_whole_mmk"),
        ("amount_received cannot be negative", "amount_received_negative"),
        ("amount_received cannot exceed total_amount", "amount_received_exceeds_total"),
        ("at least one product line is required", "product_line_required"),
    )
    return next((code for text, code in rules if text in message), "voucher_validation_failed")


PAGE = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SotePhwar Voucher</title></head><body>
<link rel="stylesheet" href="/static/farm_voucher.css">
<link rel="stylesheet" href="/static/operational_history.css"><main class="fv-app" data-operational-module="sotephwar" data-operational-api="/business-os/api/sotephwar-voucher">
  <section class="fv-panel fv-heading"><div><span>SotePhwar Sales</span><h2>SotePhwar Voucher</h2><p>Save Draft → Validate → Submit</p></div><strong id="svStatus">Draft</strong></section>
  <div id="svErrors" aria-live="polite"></div>
  <div class="fv-layout">
    <aside class="fv-panel"><div class="fv-panel-head"><h3>Voucher drafts</h3><button id="svNew" type="button">New</button></div><div id="svDrafts" class="fv-drafts"></div></aside>
    <div class="fv-workspace">
      <section class="fv-panel"><div class="fv-panel-head"><h3>New Data Entry</h3></div><div class="fv-form">
        <label>Voucher number<input id="svNumber" autocomplete="off"></label>
        <label>Invoice date<input id="svDate" type="date"></label>
        <label>Customer Master<input id="svCustomerSearch" list="svCustomerOptions" autocomplete="off" placeholder="Search name, town or phone"><datalist id="svCustomerOptions"></datalist><input id="svCustomer" type="hidden"></label>
        <label>Payment method<select id="svMethod"><option value="">Select payment type</option><option>Cash</option><option>KPay</option><option>AYA Pay</option><option>UAB Pay</option><option>Other Online Pay</option></select></label>
        <label>Amount received<input id="svReceived" type="number" min="0" step="0.01" value="0"></label>
        <section id="svCustomerDetails" class="fv-customer-details" aria-live="polite" hidden></section>
        <label class="fv-note">Note<textarea id="svNote" rows="2"></textarea></label>
      </div></section>
      <section class="fv-panel"><div class="fv-panel-head"><div><h3>Products</h3><p class="fv-help">Selling prices are editable for each line.</p></div><button id="svAddLine" type="button">Add product line</button></div>
        <div class="fv-table-wrap"><table><thead><tr><th>Product</th><th>Quantity</th><th>Unit price</th><th>Line total</th><th>Note</th><th></th></tr></thead><tbody id="svLines"></tbody></table></div>
      </section>
      <section class="fv-panel"><div class="fv-panel-head"><div><h3>Free Items (Optional)</h3><p class="fv-help">Free items do not change the voucher amount and are recorded separately.</p></div><button id="svAddFree" type="button">+ Add Free Item</button></div><div class="fv-table-wrap"><table><thead><tr><th>Product</th><th>Quantity</th><th>Note</th><th></th></tr></thead><tbody id="svFreeLines"></tbody></table></div></section>
      <section class="fv-panel"><h3>Adjustment (Optional)</h3><div class="fv-form"><label>Discount (MMK)<input id="svDiscount" type="number" min="0" step="1" value="0"></label><label>Cashback (MMK)<input id="svCashback" type="number" min="0" step="1" value="0"></label><label class="fv-note">Adjustment Reason<textarea id="svAdjustmentReason" rows="2"></textarea></label></div><p class="fv-total">Gross Total <strong id="svGross">0 MMK</strong><br><small>Discount <span id="svDiscountTotal">0 MMK</span> · Cashback <span id="svCashbackTotal">0 MMK</span><br>Net Amount <span id="svNet">0 MMK</span> · Received <span id="svReceivedTotal">0 MMK</span> · Outstanding <span id="svOutstanding">0 MMK</span></small></p><span id="svTotal" hidden></span></section>
      <div class="fv-actions"><button id="svSave">Save Draft</button><button id="svValidate">Validate</button><button id="svPrint" disabled><span aria-hidden="true">🖨</span> Print</button><button id="svSavePdf" disabled><span aria-hidden="true">⬇</span> Save PDF</button><button id="svSubmit" class="fv-submit" disabled>Submit to SotePhwar Transactions</button><span id="svPreview" hidden></span><span id="svPdf" hidden></span></div>
      <section id="svSubmittedPanel" class="fv-panel fv-preview" hidden></section>
    </div>
  </div>
  <section id="opSummary" class="op-summary"></section><section class="fv-panel"><div class="fv-panel-head"><h3>Saved Drafts</h3></div><div id="opDrafts" class="op-drafts"></div></section><section class="fv-panel"><div class="fv-panel-head"><h3>Recent Voucher Insertion History</h3></div><div class="op-history-filters"><input data-op-filter="date_from" type="date"><input data-op-filter="date_to" type="date"><input data-op-filter="customer" placeholder="Customer"><input data-op-filter="voucher_number" placeholder="Voucher number"><select data-op-filter="payment_status"><option value="">All payment statuses</option><option>Paid</option><option>Partial</option><option>Outstanding</option></select></div><div id="opHistory" class="op-table"></div><div class="op-paging"><button id="opPrev">Previous</button><span id="opPageInfo"></span><button id="opNext">Next</button><select id="opPageSize"><option>20</option><option>50</option><option>100</option></select></div></section>
</main><dialog id="opRemoveModal" class="op-modal"><h3>Remove Draft</h3><p>Remove this draft? This action removes only the unsubmitted draft. It does not affect any submitted voucher, transaction or inventory record.</p><textarea id="opRemoveReason" placeholder="Optional reason"></textarea><div class="op-actions"><button onclick="this.closest('dialog').close()">Cancel</button><button id="opRemoveConfirm" class="op-remove">Remove Draft</button></div></dialog><dialog id="opDeleteVoucherModal" class="op-modal"><h3>Delete Submitted Voucher</h3><p>This permanently removes the selected voucher submission and its linked SotePhwar transaction rows. Vouchers with payment history are protected.</p><p>Type voucher number <strong id="opDeleteVoucherNumber"></strong> to confirm.</p><input id="opDeleteVoucherConfirm" autocomplete="off" placeholder="Voucher number"><textarea id="opDeleteVoucherReason" placeholder="Deletion reason (required)"></textarea><div class="op-actions"><button onclick="this.closest('dialog').close()">Cancel</button><button id="opDeleteVoucherSubmit" class="op-remove">Delete Voucher</button></div></dialog><dialog id="opDetailModal" class="op-modal"><h3>Submission Details</h3><pre id="opDetailBody"></pre><button onclick="this.closest('dialog').close()">Close</button></dialog><script src="/static/business_os_uuid.js?v=20260720-2"></script><script src="/static/sotephwar_voucher.js?v=20260721-adjustments1"></script><script src="/static/operational_history.js?v=20260722-delete2"></script></body></html>'''


def _error(exc):
    if isinstance(exc, voucher_engine.VoucherValidationError):
        code = _validation_code(exc.errors)
        reason = str((exc.errors or ["Voucher validation failed"])[0])
        LOGGER.warning("SotePhwar validation failed code=%s errors=%s", code, exc.errors)
        return jsonify({"ok": False, "error": reason, "code": code, "errors": exc.errors}), 400
    if isinstance(exc, LookupError):
        LOGGER.warning("SotePhwar request failed code=draft_not_found error=%s", exc)
        return jsonify({"ok": False, "error": str(exc), "code": "draft_not_found"}), 404
    if isinstance(exc, (ValueError, RuntimeError, TypeError)):
        LOGGER.warning("SotePhwar request failed code=invalid_request error=%s", exc)
        return jsonify({"ok": False, "error": str(exc), "code": "invalid_request"}), 400
    LOGGER.exception("SotePhwar Voucher operation failed", exc_info=exc)
    return jsonify({"ok": False, "error": "SotePhwar Voucher operation failed", "code": "internal_error"}), 500


def register_sotephwar_voucher(app):
    page = lambda: (PAGE, 200, {"Cache-Control": "no-store"})
    app.add_url_rule("/sotephwar-voucher", "sotephwar_voucher_page", page, methods=["GET"])
    app.add_url_rule("/business-os/sotephwar-voucher", "business_os_sotephwar_voucher", page, methods=["GET"])
    api = "/business-os/api/sotephwar-voucher"

    app.add_url_rule(f"{api}/products", "business_os_sotephwar_voucher_products", lambda: jsonify({"ok": True, "products": sotephwar_voucher_repository.products()}), methods=["GET"])

    def customers():
        try: return jsonify({"ok": True, "customers": sotephwar_voucher_repository.list_customers()})
        except Exception as exc: return _error(exc)
    app.add_url_rule(f"{api}/customers", "business_os_sotephwar_voucher_customers", customers, methods=["GET"])

    def drafts():
        try: return jsonify({"ok": True, "drafts": sotephwar_voucher_repository.list_drafts()})
        except Exception as exc: return _error(exc)
    app.add_url_rule(f"{api}/drafts", "business_os_sotephwar_voucher_drafts", drafts, methods=["GET"])

    def create():
        try: return jsonify({"ok": True, "draft": sotephwar_voucher_repository.create_draft(request.get_json(silent=True) or {}, "Business OS")}), 201
        except Exception as exc: return _error(exc)
    app.add_url_rule(f"{api}/drafts", "business_os_create_sotephwar_voucher_draft", create, methods=["POST"])

    def get(draft_id):
        try:
            draft = sotephwar_voucher_repository.get_draft(draft_id)
            if not draft: raise LookupError("SotePhwar voucher draft not found")
            return jsonify({"ok": True, "draft": draft})
        except Exception as exc: return _error(exc)
    app.add_url_rule(f"{api}/drafts/<int:draft_id>", "business_os_get_sotephwar_voucher_draft", get, methods=["GET"])

    def update(draft_id):
        try:
            body = request.get_json(silent=True) or {}
            return jsonify({"ok": True, "draft": sotephwar_voucher_repository.update_draft(draft_id, body, body.get("version"))})
        except Exception as exc: return _error(exc)
    app.add_url_rule(f"{api}/drafts/<int:draft_id>", "business_os_update_sotephwar_voucher_draft", update, methods=["PUT"])

    for action in ("validate", "preview"):
        def workflow(draft_id, action=action):
            try:
                state = "previewed"
                result = sotephwar_voucher_repository.set_workflow_state(draft_id, state)
                payload = {"ok": True, **result}
                if action == "preview":
                    version = result.get("draft", {}).get("version", "")
                    payload["pdf_url"] = url_for(
                        "business_os_sotephwar_voucher_pdf", draft_id=draft_id,
                        inline=1, version=version, _external=False,
                    )
                return jsonify(payload)
            except Exception as exc: return _error(exc)
        app.add_url_rule(f"{api}/drafts/<int:draft_id>/{action}", f"business_os_sotephwar_voucher_{action}", workflow, methods=["POST"])

    def pdf(draft_id):
        try:
            draft = sotephwar_voucher_repository.get_draft(draft_id)
            if not draft: raise LookupError("SotePhwar voucher draft not found")
            if draft.get("status") == "submitted":
                path = sotephwar_voucher_repository.submitted_pdf_path(draft)
                voucher = draft.get("submitted_voucher") or draft
            else:
                voucher = voucher_engine.preview_sotephwar(draft.get("submitted_voucher") or draft)
                handle = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
                path = Path(handle.name); handle.close()
                write_sotephwar_voucher_pdf(voucher, path)
            return send_file(path, as_attachment=request.args.get("inline") != "1", download_name=f'SotePhwar_Voucher_{voucher["voucher_number"]}.pdf', mimetype="application/pdf")
        except Exception as exc: return _error(exc)
    app.add_url_rule(f"{api}/drafts/<int:draft_id>/pdf", "business_os_sotephwar_voucher_pdf", pdf, methods=["GET"])

    def submit(draft_id):
        try: return jsonify({"ok": True, **sotephwar_voucher_repository.submit(draft_id, "Business OS")})
        except Exception as exc: return _error(exc)
    app.add_url_rule(f"{api}/drafts/<int:draft_id>/submit", "business_os_submit_sotephwar_voucher", submit, methods=["POST"])

    def remove(draft_id):
        if request.headers.get("X-Business-OS-Request") != "draft-management-v1": return jsonify({"ok":False,"error":"Protected Business OS endpoint"}),403
        try:return jsonify({"ok":True,**sotephwar_voucher_repository.remove_draft(draft_id,"Business OS",(request.get_json(silent=True) or {}).get("reason",""))})
        except Exception as exc:return _error(exc)
    app.add_url_rule(f"{api}/drafts/<int:draft_id>/remove","business_os_remove_sotephwar_voucher_draft",remove,methods=["POST"])

    def history():
        filters = None
        try:
            filters, page, page_size = _history_request_args(request.args)
            return jsonify({"ok": True, **sotephwar_voucher_repository.recent_submissions(filters, page, page_size)})
        except Exception as exc:
            LOGGER.warning(
                "SotePhwar history request failed error=%r query=%s normalized_filters=%s",
                exc, request.args.to_dict(flat=True), filters,
            )
            return _error(exc)
    app.add_url_rule(f"{api}/history","business_os_sotephwar_voucher_history",history,methods=["GET"])

    def history_detail(draft_id):
        try:return jsonify({"ok":True,"submission":sotephwar_voucher_repository.submission_details(draft_id)})
        except Exception as exc:return _error(exc)
    app.add_url_rule(f"{api}/history/<int:draft_id>","business_os_sotephwar_voucher_history_detail",history_detail,methods=["GET"])

    def delete_history(draft_id):
        if request.headers.get("X-Business-OS-Request") != "draft-management-v1":
            return jsonify({"ok": False, "error": "Protected Business OS endpoint"}), 403
        try:
            body = request.get_json(silent=True) or {}
            result = sotephwar_voucher_repository.delete_submitted_voucher(
                draft_id,
                body.get("confirmation") or body.get("voucher_number"),
                body.get("reason"),
                "Business OS",
            )
            pdf_path = result.pop("pdf_path", None)
            pdf_removed = False
            pdf_cleanup_warning = False
            if pdf_path:
                path = Path(pdf_path)
                if path.is_file():
                    try:
                        path.unlink()
                        pdf_removed = True
                    except OSError:
                        pdf_cleanup_warning = True
                        LOGGER.exception(
                            "Voucher database deletion committed but PDF cleanup failed draft_id=%s",
                            result["draft_id"],
                        )
            LOGGER.warning(
                "SotePhwar submitted voucher deleted draft_id=%s voucher_number=%s customer=%s transaction_ids=%s reason=%s pdf_removed=%s",
                result["draft_id"], result["voucher_number"], result["customer_name"],
                result["transaction_ids"], result["reason"], pdf_removed,
            )
            return jsonify({
                "ok": True, **result, "pdf_removed": pdf_removed,
                "pdf_cleanup_warning": pdf_cleanup_warning,
            })
        except Exception as exc:
            return _error(exc)
    app.add_url_rule(
        f"{api}/history/<int:draft_id>/delete",
        "business_os_sotephwar_voucher_history_delete",
        delete_history,
        methods=["POST"],
    )

    def summary():
        try:return jsonify({"ok":True,"summary":sotephwar_voucher_repository.operational_summary()})
        except Exception as exc:return _error(exc)
    app.add_url_rule(f"{api}/summary","business_os_sotephwar_voucher_summary",summary,methods=["GET"])
