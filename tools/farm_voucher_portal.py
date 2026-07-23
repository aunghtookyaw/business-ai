"""Farm Voucher routes mounted in the local BigShot Business OS service."""
import logging
import tempfile
from copy import deepcopy
from pathlib import Path

from flask import after_this_request, jsonify, request, send_file, url_for

from tools import farm_voucher_repository, voucher_engine
from tools.payment_state import current_voucher_payment_state
from tools.farm_voucher_pdf import write_farm_voucher_pdf


LOGGER = logging.getLogger(__name__)


PAGE = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Farm Voucher</title></head><body>
<link rel="stylesheet" href="/static/farm_voucher.css">
<link rel="stylesheet" href="/static/operational_history.css"><main class="fv-app" data-operational-module="farm" data-operational-api="/business-os/api/farm-voucher">
  <section class="fv-panel fv-heading"><div><span>Farm Sales</span><h2>Farm Voucher</h2><p>Save Draft → Validate → Submit</p></div><strong id="fvStatus">Draft</strong></section>
  <div id="fvErrors" aria-live="polite"></div>
  <div class="fv-layout">
    <aside class="fv-panel"><div class="fv-panel-head"><h3>Voucher drafts</h3><button id="fvNew" type="button">New</button></div><div id="fvDrafts" class="fv-drafts"></div></aside>
    <div class="fv-workspace">
      <section class="fv-panel"><div class="fv-panel-head"><h3>New Data Entry</h3></div><div class="fv-form">
        <label>Voucher number<input id="fvNumber" inputmode="numeric" autocomplete="off"></label>
        <label>Invoice Date<input id="fvDate" type="date"></label>
        <label>Customer Master<input id="fvCustomerSearch" list="fvCustomerOptions" autocomplete="off" placeholder="Search name, town or phone"><datalist id="fvCustomerOptions"></datalist><input id="fvCustomer" type="hidden"></label>
        <label>Payment method<select id="fvMethod"><option value="">Select payment type</option><option>Cash</option><option>KPay</option><option>AYA Pay</option><option>UAB Pay</option><option>Other Online Pay</option></select></label>
        <label>Amount received<input id="fvReceived" type="number" min="0" step="0.01" value="0"></label>
        <section id="fvCustomerDetails" class="fv-customer-details" aria-live="polite" hidden></section>
        <label class="fv-note">Note<textarea id="fvNote" rows="2"></textarea></label>
      </div></section>
      <section class="fv-panel"><div class="fv-panel-head"><div><h3>Dated deliveries</h3><p class="fv-help">One invoice can combine several delivery dates and prices.</p></div><button id="fvAddSection" type="button">Add Date Section</button></div><div id="fvSections" class="fv-sections"></div></section>
      <section class="fv-panel"><h3>Adjustment (Optional)</h3><div class="fv-form"><label>Discount (MMK)<input id="fvDiscount" type="number" min="0" step="1" value="0"></label><label>Cashback (MMK)<input id="fvCashback" type="number" min="0" step="1" value="0"></label><label class="fv-note">Adjustment Reason<textarea id="fvAdjustmentReason" rows="2"></textarea></label></div><p class="fv-total">Gross Total <strong id="fvGross">0 MMK</strong><br><small>Discount <span id="fvDiscountTotal">0 MMK</span> · Cashback <span id="fvCashbackTotal">0 MMK</span><br>Net Amount <span id="fvNet">0 MMK</span> · Received <span id="fvReceivedTotal">0 MMK</span> · Outstanding <span id="fvOutstanding">0 MMK</span></small></p><span id="fvTotal" hidden></span></section>
      <div class="fv-actions"><button id="fvSave">Save draft</button><button id="fvValidate">Validate</button><button id="fvPrint" disabled><span aria-hidden="true">🖨</span> Print</button><button id="fvSavePdf" disabled><span aria-hidden="true">⬇</span> Save PDF</button><button id="fvSubmit" class="fv-submit" disabled>Submit to Farm transactions</button><span id="fvPreview" hidden></span><span id="fvPdf" hidden></span></div>
      <section id="fvSubmittedPanel" class="fv-panel fv-preview" hidden></section>
    </div>
  </div>
  <section id="opSummary" class="op-summary"></section>
  <section class="fv-panel"><div class="fv-panel-head"><h3>Saved Drafts</h3></div><div id="opDrafts" class="op-drafts"></div></section>
  <section class="fv-panel"><div class="fv-panel-head"><h3>Recent Voucher Insertion History</h3></div><div class="op-history-filters"><input data-op-filter="date_from" type="date" aria-label="Date from"><input data-op-filter="date_to" type="date" aria-label="Date to"><input data-op-filter="customer" placeholder="Customer"><input data-op-filter="voucher_number" placeholder="Voucher number"><select data-op-filter="payment_status"><option value="">All payment statuses</option><option>Paid</option><option>Partial</option><option>Outstanding</option></select></div><div id="opHistory" class="op-table"></div><div class="op-paging"><button id="opPrev">Previous</button><span id="opPageInfo"></span><button id="opNext">Next</button><select id="opPageSize"><option>20</option><option>50</option><option>100</option></select></div></section>
</main><dialog id="opRemoveModal" class="op-modal"><h3>Remove Draft</h3><p>Remove this draft? This action removes only the unsubmitted draft. It does not affect any submitted voucher, transaction or inventory record.</p><textarea id="opRemoveReason" placeholder="Optional reason"></textarea><div class="op-actions"><button onclick="this.closest('dialog').close()">Cancel</button><button id="opRemoveConfirm" class="op-remove">Remove Draft</button></div></dialog><dialog id="opDeleteVoucherModal" class="op-modal"><h3>Delete Submitted Voucher</h3><p>This permanently removes the selected voucher and its linked Farm transaction. Vouchers with payment history are protected.</p><p>Type voucher number <strong id="opDeleteVoucherNumber"></strong> to confirm.</p><input id="opDeleteVoucherConfirm" autocomplete="off"><textarea id="opDeleteVoucherReason" placeholder="Deletion reason (required)"></textarea><div class="op-actions"><button onclick="this.closest('dialog').close()">Cancel</button><button id="opDeleteVoucherSubmit" class="op-remove">Delete</button></div></dialog><dialog id="opDetailModal" class="op-modal"><h3>Submission Details</h3><pre id="opDetailBody"></pre><button onclick="this.closest('dialog').close()">Close</button></dialog><script src="/static/business_os_uuid.js?v=20260720-2"></script><script src="/static/farm_voucher.js?v=20260721-adjustments1"></script><script src="/static/operational_history.js?v=20260722-delete2"></script></body></html>'''


def _error(exc):
    if isinstance(exc, voucher_engine.VoucherValidationError):
        return jsonify({"ok": False, "error": "Validation failed", "errors": exc.errors}), 400
    if isinstance(exc, LookupError):
        return jsonify({"ok": False, "error": str(exc)}), 404
    if isinstance(exc, (ValueError, RuntimeError, TypeError)):
        return jsonify({"ok": False, "error": str(exc)}), 400
    LOGGER.exception("Farm Voucher operation failed", exc_info=exc)
    return jsonify({"ok": False, "error": "Farm Voucher operation failed"}), 500


def register_farm_voucher(app):
    page = lambda: (PAGE, 200, {"Cache-Control": "no-store"})
    app.add_url_rule("/farm-voucher", "farm_voucher_page", page, methods=["GET"])
    app.add_url_rule("/business-os/farm-voucher", "business_os_farm_voucher", page, methods=["GET"])

    @app.get("/business-os/api/farm-voucher/customers")
    def business_os_farm_voucher_customers():
        try:
            return jsonify({"ok": True, "customers": farm_voucher_repository.list_customers()})
        except Exception as exc:
            return _error(exc)

    @app.get("/business-os/api/farm-voucher/crops")
    def business_os_farm_voucher_crops():
        try:
            return jsonify({"ok": True, "crops": farm_voucher_repository.list_crops()})
        except Exception as exc:
            return _error(exc)

    @app.get("/business-os/api/farm-voucher/drafts")
    def business_os_farm_voucher_drafts():
        try:
            return jsonify({"ok": True, "drafts": farm_voucher_repository.list_drafts()})
        except Exception as exc:
            return _error(exc)

    @app.post("/business-os/api/farm-voucher/drafts")
    def business_os_create_farm_voucher_draft():
        try:
            return jsonify({"ok": True, "draft": farm_voucher_repository.create_draft(request.get_json(silent=True) or {}, "Business OS")}), 201
        except Exception as exc:
            return _error(exc)

    @app.get("/business-os/api/farm-voucher/drafts/<int:draft_id>")
    def business_os_get_farm_voucher_draft(draft_id):
        try:
            draft = farm_voucher_repository.get_draft(draft_id)
            if not draft:
                raise LookupError("Farm voucher draft not found")
            return jsonify({"ok": True, "draft": draft})
        except Exception as exc:
            return _error(exc)

    @app.put("/business-os/api/farm-voucher/drafts/<int:draft_id>")
    def business_os_update_farm_voucher_draft(draft_id):
        try:
            body = request.get_json(silent=True) or {}
            return jsonify({"ok": True, "draft": farm_voucher_repository.update_draft(draft_id, body, body.get("version"))})
        except Exception as exc:
            return _error(exc)

    for action in ("validate", "preview"):
        def workflow(draft_id, action=action):
            try:
                state = "previewed"
                result = farm_voucher_repository.set_workflow_state(draft_id, state)
                payload = {"ok": True, **result}
                if action == "preview":
                    version = result.get("draft", {}).get("version", "")
                    payload["pdf_url"] = url_for(
                        "business_os_farm_voucher_pdf", draft_id=draft_id,
                        inline=1, version=version, _external=False,
                    )
                return jsonify(payload)
            except Exception as exc:
                return _error(exc)
        app.add_url_rule(
            f"/business-os/api/farm-voucher/drafts/<int:draft_id>/{action}",
            f"business_os_farm_voucher_{action}", workflow, methods=["POST"],
        )

    @app.get("/business-os/api/farm-voucher/drafts/<int:draft_id>/pdf")
    def business_os_farm_voucher_pdf(draft_id):
        try:
            draft = farm_voucher_repository.get_draft(draft_id)
            if not draft:
                raise LookupError("Farm voucher draft not found")
            if draft.get("status") == "submitted":
                original_path = farm_voucher_repository.submitted_pdf_path(draft)
                voucher = deepcopy(draft.get("submitted_voucher") or draft)
                if request.args.get("original") == "1":
                    path = original_path
                else:
                    current = current_voucher_payment_state(
                        "Farm", voucher["voucher_number"],
                        invoice_date=voucher.get("voucher_date"), customer=voucher.get("customer_name"),
                    )
                    voucher["amount_received"] = current["current_received"]
                    voucher["outstanding_balance"] = current["current_outstanding"]
                    voucher["payment_status"] = current["current_payment_status"]
                    voucher["latest_payment_date"] = current["latest_payment_date"]
                    handle = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
                    path = Path(handle.name)
                    handle.close()
                    write_farm_voucher_pdf(voucher, path)
                    @after_this_request
                    def remove_current_statement(response):
                        try:
                            path.unlink(missing_ok=True)
                        except OSError:
                            LOGGER.exception("Could not remove temporary current Farm statement %s", path)
                        return response
            else:
                voucher = voucher_engine.preview(draft.get("submitted_voucher") or draft)
                handle = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
                path = Path(handle.name)
                handle.close()
                write_farm_voucher_pdf(voucher, path)
            inline = request.args.get("inline") == "1"
            return send_file(path, as_attachment=not inline, download_name=f'Farm_Voucher_{voucher["voucher_number"]}.pdf', mimetype="application/pdf")
        except Exception as exc:
            return _error(exc)

    @app.post("/business-os/api/farm-voucher/drafts/<int:draft_id>/submit")
    def business_os_submit_farm_voucher(draft_id):
        try:
            return jsonify({"ok": True, **farm_voucher_repository.submit(draft_id, "Business OS")})
        except Exception as exc:
            return _error(exc)

    @app.post("/business-os/api/farm-voucher/drafts/<int:draft_id>/remove")
    def business_os_remove_farm_voucher_draft(draft_id):
        if request.headers.get("X-Business-OS-Request") != "draft-management-v1": return jsonify({"ok":False,"error":"Protected Business OS endpoint"}),403
        try:
            body=request.get_json(silent=True) or {}
            return jsonify({"ok":True,**farm_voucher_repository.remove_draft(draft_id,"Business OS",body.get("reason",""))})
        except Exception as exc:return _error(exc)

    @app.get("/business-os/api/farm-voucher/history")
    def business_os_farm_voucher_history():
        try:return jsonify({"ok":True,**farm_voucher_repository.recent_submissions(request.args,request.args.get("page",1),request.args.get("page_size",20))})
        except Exception as exc:return _error(exc)

    @app.get("/business-os/api/farm-voucher/history/<int:draft_id>")
    def business_os_farm_voucher_history_detail(draft_id):
        try:return jsonify({"ok":True,"submission":farm_voucher_repository.submission_details(draft_id)})
        except Exception as exc:return _error(exc)

    @app.post("/business-os/api/farm-voucher/history/<int:draft_id>/delete")
    def business_os_farm_voucher_history_delete(draft_id):
        if request.headers.get("X-Business-OS-Request") != "draft-management-v1": return jsonify({"ok":False,"error":"Protected Business OS endpoint"}),403
        try:
            body=request.get_json(silent=True) or {}
            result=farm_voucher_repository.delete_submitted_voucher(draft_id,body.get("confirmation") or body.get("voucher_number"),body.get("reason"),"Business OS")
            pdf=result.pop("pdf_path",None); removed=False
            if pdf and Path(pdf).is_file():
                try: Path(pdf).unlink(); removed=True
                except OSError: LOGGER.exception("Farm voucher deleted but PDF cleanup failed draft_id=%s",draft_id)
            LOGGER.warning("Farm submitted voucher deleted draft_id=%s voucher=%s reason=%s",draft_id,result["voucher_number"],result["reason"])
            return jsonify({"ok":True,**result,"pdf_removed":removed})
        except Exception as exc:return _error(exc)

    @app.get("/business-os/api/farm-voucher/summary")
    def business_os_farm_voucher_summary():
        try:
            response = jsonify({"ok":True,"summary":farm_voucher_repository.operational_summary()})
            response.headers["Cache-Control"] = "no-store"
            return response
        except Exception as exc:return _error(exc)
