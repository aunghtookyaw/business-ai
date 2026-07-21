"""General Transaction routes mounted in BigShot Business OS."""
from pathlib import Path
from uuid import uuid4

from flask import jsonify, request
from werkzeug.utils import secure_filename

from tools import general_transaction


ROOT = Path(__file__).resolve().parents[1]
ATTACHMENT_DIR = ROOT / "output" / "general_transaction_attachments"

PAGE = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>General Transaction</title></head><body>
<link rel="stylesheet" href="/static/general_transaction.css"><link rel="stylesheet" href="/static/operational_history.css">
<main class="gt-app" data-operational-module="general" data-operational-api="/business-os/api/general-transaction">
 <section class="gt-panel gt-heading"><div><span>Financial</span><h2>General Transaction</h2><p>Non-voucher income and general expenses</p></div><strong id="gtStatus">Draft</strong></section>
 <div id="gtMessage" aria-live="polite"></div><div id="gtErrors" aria-live="assertive"></div>
 <section class="gt-panel"><h3>New General Transaction</h3><form id="gtForm" enctype="multipart/form-data"><div class="gt-grid">
  <label>Transaction Date<input id="gtDate" name="transaction_date" type="date" required></label>
  <label>Type<select id="gtType" name="transaction_type" required><option value="">Select type</option><option>Income</option><option>Expense</option></select></label>
  <label>Sector<select id="gtSector" name="sector" required><option value="">Select sector</option><option>Farm</option><option>Sote Phwar</option></select></label>
  <label>Category<input id="gtCategorySearch" list="gtCategoryOptions" autocomplete="off" placeholder="Search code or category" required><datalist id="gtCategoryOptions"></datalist><input id="gtCategory" name="category_id" type="hidden"></label>
  <label class="gt-wide">Description<input id="gtDescription" name="description" autocomplete="off" required></label>
  <label>Amount (MMK)<input id="gtAmount" name="amount" type="number" min="1" step="1" inputmode="numeric" required></label>
  <label>Payment Method<select id="gtMethod" name="payment_method" required><option value="">Select payment type</option><option>Cash</option><option>KPay</option><option>AYA Pay</option><option>UAB Pay</option><option>Other Online Pay</option></select></label>
  <label>Receipt / Attachment<input id="gtAttachment" name="attachment" type="file"></label>
  <label class="gt-wide">Comment<textarea id="gtComment" name="comment" rows="3"></textarea></label>
 </div></form><div class="gt-actions"><button id="gtNew" type="button">New</button><button id="gtSave" type="button">Save Draft</button><button id="gtValidate" type="button">Validate</button><button id="gtConfirm" class="gt-submit" type="button" disabled>Confirm & Submit</button></div><p class="gt-warning">Confirm only genuine non-voucher income or a general expense. Submitted records cannot be edited; guarded deletion is available in Recent Transaction Insertions.</p></section>
 <section id="opSummary" class="op-summary"></section><section class="gt-panel"><div class="gt-panel-head"><h3>Saved Transaction Drafts</h3></div><div id="opDrafts" class="op-drafts"></div></section><section class="gt-panel"><div class="gt-panel-head"><h3>Recent Transaction Insertions</h3></div><div class="op-history-filters"><input data-op-filter="date_from" type="date"><input data-op-filter="date_to" type="date"><select data-op-filter="transaction_type"><option value="">All types</option><option>Income</option><option>Expense</option></select><select data-op-filter="sector"><option value="">All sectors</option><option>Farm</option><option>Sote Phwar</option></select><select id="gtFilterCategory" data-op-filter="category_id"><option value="">All categories</option></select></div><div id="opHistory" class="op-table"></div><div class="op-paging"><button id="opPrev">Previous</button><span id="opPageInfo"></span><button id="opNext">Next</button><select id="opPageSize"><option>20</option><option>50</option><option>100</option></select></div></section>
</main>
<dialog id="gtModal"><form method="dialog"><h3>Submit General Transaction?</h3><p>This accounting entry will be permanent in this module.</p><div id="gtModalSummary"></div><div class="gt-actions"><button value="cancel">Cancel</button><button id="gtModalSubmit" value="default" class="gt-submit">Submit</button></div></form></dialog>
<dialog id="opRemoveModal" class="op-modal"><h3>Remove Draft</h3><p>Remove this draft? This action removes only the unsubmitted draft. It does not affect any submitted voucher, transaction or inventory record.</p><textarea id="opRemoveReason" placeholder="Optional reason"></textarea><div class="op-actions"><button onclick="this.closest('dialog').close()">Cancel</button><button id="opRemoveConfirm" class="op-remove">Remove Draft</button></div></dialog><dialog id="opDeleteVoucherModal" class="op-modal"><h3>Delete Submitted Transaction</h3><p>This permanently removes the selected General Transaction and its category link.</p><p>Type transaction ID <strong id="opDeleteVoucherNumber"></strong> to confirm.</p><input id="opDeleteVoucherConfirm" autocomplete="off"><textarea id="opDeleteVoucherReason" placeholder="Deletion reason (required)"></textarea><div class="op-actions"><button onclick="this.closest('dialog').close()">Cancel</button><button id="opDeleteVoucherSubmit" class="op-remove">Delete</button></div></dialog><dialog id="opDetailModal" class="op-modal"><h3>Submission Details</h3><pre id="opDetailBody"></pre><button onclick="this.closest('dialog').close()">Close</button></dialog><script src="/static/general_transaction.js?v=20260722-validate1"></script><script src="/static/operational_history.js?v=20260722-general1"></script></body></html>'''


def _error(exc):
    if isinstance(exc, general_transaction.GeneralTransactionValidationError):
        return jsonify({"ok": False, "error": "Validation failed", "errors": exc.errors}), 400
    if isinstance(exc, LookupError): return jsonify({"ok": False, "error": str(exc)}), 404
    if isinstance(exc, (ValueError, RuntimeError, TypeError)): return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": False, "error": "General Transaction operation failed"}), 500


def _values():
    source = request.form if request.form else (request.get_json(silent=True) or {})
    return {key: source.get(key) for key in (
        "transaction_date", "transaction_type", "sector", "category_id", "description",
        "amount", "payment_method", "comment", "version",
    )}


def _save_attachment(file):
    if not file or not file.filename: return "", ""
    original = secure_filename(file.filename)
    if not original: raise ValueError("Attachment filename is invalid")
    ATTACHMENT_DIR.mkdir(parents=True, exist_ok=True)
    stored = f"{uuid4()}-{original}"
    path = ATTACHMENT_DIR / stored
    file.save(path)
    return str(path.relative_to(ROOT)), original


def register_general_transaction(app):
    app.add_url_rule("/business-os/general-transaction", "business_os_general_transaction", lambda: PAGE, methods=["GET"])

    @app.get("/business-os/api/general-transaction/categories")
    def general_transaction_categories():
        try: return jsonify({"ok": True, "categories": general_transaction.list_categories()})
        except Exception as exc: return _error(exc)

    @app.get("/business-os/api/general-transaction/drafts")
    def general_transaction_drafts():
        try: return jsonify({"ok": True, "drafts": general_transaction.list_drafts()})
        except Exception as exc: return _error(exc)

    @app.post("/business-os/api/general-transaction/drafts")
    def general_transaction_create():
        path = name = ""
        try:
            path, name = _save_attachment(request.files.get("attachment"))
            values = {**_values(), "attachment_path": path, "attachment_name": name}
            return jsonify({"ok": True, "draft": general_transaction.create_draft(values, "Business OS")})
        except Exception as exc:
            if path: (ROOT / path).unlink(missing_ok=True)
            return _error(exc)

    @app.get("/business-os/api/general-transaction/drafts/<int:draft_id>")
    def general_transaction_get(draft_id):
        try:
            draft=general_transaction.get_draft(draft_id)
            if not draft:raise LookupError("General Transaction draft not found")
            return jsonify({"ok":True,"draft":draft})
        except Exception as exc:return _error(exc)

    @app.put("/business-os/api/general-transaction/drafts/<int:draft_id>")
    def general_transaction_update(draft_id):
        path = name = ""
        try:
            current = general_transaction.get_draft(draft_id)
            path, name = _save_attachment(request.files.get("attachment"))
            values = _values()
            values.update({"attachment_path": path or current.get("attachment_path", ""), "attachment_name": name or current.get("attachment_name", "")})
            return jsonify({"ok": True, "draft": general_transaction.update_draft(draft_id, values, values.get("version"))})
        except Exception as exc:
            if path: (ROOT / path).unlink(missing_ok=True)
            return _error(exc)

    @app.post("/business-os/api/general-transaction/drafts/<int:draft_id>/<state>")
    def general_transaction_state(draft_id, state):
        try:
            result = general_transaction.set_workflow_state(draft_id, state)
            return jsonify({"ok": True, **result})
        except Exception as exc: return _error(exc)

    @app.post("/business-os/api/general-transaction/drafts/<int:draft_id>/submit")
    def general_transaction_submit(draft_id):
        try:
            payload = request.get_json(silent=True) or {}
            result = general_transaction.submit(draft_id, payload.get("submission_key"), "Business OS")
            return jsonify({"ok": True, **result})
        except Exception as exc: return _error(exc)

    @app.get("/business-os/api/general-transaction/recent")
    def general_transaction_recent():
        try:
            filters = {key: request.args.get(key) for key in ("date_from", "date_to", "transaction_type", "sector", "category_id")}
            return jsonify({"ok": True, **general_transaction.recent_transactions(filters,request.args.get("page",1),request.args.get("page_size",20))})
        except Exception as exc: return _error(exc)

    @app.post("/business-os/api/general-transaction/drafts/<int:draft_id>/remove")
    def general_transaction_remove(draft_id):
        if request.headers.get("X-Business-OS-Request") != "draft-management-v1": return jsonify({"ok":False,"error":"Protected Business OS endpoint"}),403
        try:return jsonify({"ok":True,**general_transaction.remove_draft(draft_id,"Business OS",(request.get_json(silent=True) or {}).get("reason",""))})
        except Exception as exc:return _error(exc)

    @app.get("/business-os/api/general-transaction/history/<int:draft_id>")
    def general_transaction_history_detail(draft_id):
        try:return jsonify({"ok":True,"submission":general_transaction.submission_details(draft_id)})
        except Exception as exc:return _error(exc)

    @app.post("/business-os/api/general-transaction/history/<int:draft_id>/delete")
    def general_transaction_history_delete(draft_id):
        if request.headers.get("X-Business-OS-Request") != "draft-management-v1": return jsonify({"ok":False,"error":"Protected Business OS endpoint"}),403
        try:
            body=request.get_json(silent=True) or {}
            result=general_transaction.delete_submitted_transaction(draft_id,body.get("confirmation"),body.get("reason"),"Business OS")
            attachment=result.pop("attachment_path",None); removed=False
            if attachment:
                path=ROOT/attachment
                if path.is_file():
                    try:path.unlink();removed=True
                    except OSError:pass
            return jsonify({"ok":True,**result,"attachment_removed":removed})
        except Exception as exc:return _error(exc)

    @app.get("/business-os/api/general-transaction/summary")
    def general_transaction_summary():
        try:return jsonify({"ok":True,"summary":general_transaction.operational_summary()})
        except Exception as exc:return _error(exc)
