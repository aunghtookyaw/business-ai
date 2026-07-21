"""Native Business OS page and protected APIs for SotePhwar inventory movements."""
from flask import jsonify, request

from tools import sotephwar_inventory


API_HEADER = "inventory-v1"
PAGE = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SotePhwar Inventory</title></head><body>
<link rel="stylesheet" href="/static/sotephwar_inventory.css?v=20260718-2">
<link rel="stylesheet" href="/static/operational_history.css"><main class="si-app" data-operational-module="inventory" data-operational-api="/business-os/api/sotephwar-inventory">
  <section class="si-heading"><div><span>Inventory Operations</span><h2>SotePhwar Inventory</h2><p>Production, transfers and sales recorded against the authoritative movement ledger.</p></div><div class="si-heading-actions"><strong class="si-status">Live Stock</strong><button id="siRefresh" type="button">Refresh</button></div></section>
  <div id="siErrors" aria-live="polite"></div>
  <section class="si-kpis" aria-label="Current stock summary"><article class="si-kpi si-kpi-total"><span>Total Bottles</span><strong id="siTotal">—</strong><small>all products</small></article><div id="siProductCards" class="si-product-cards"></div></section>
  <section class="si-panel"><div class="si-panel-head"><div><h3>Stock by store and product</h3><p>Authoritative bottle quantities. Low and zero labels are visual indicators only.</p></div></div><div class="si-table-wrap"><table id="siMatrix"><thead></thead><tbody></tbody></table></div></section>
  <section class="si-grid">
    <section class="si-panel"><div class="si-panel-head"><div><h3>New Inventory Movement</h3><p>Draft → Validate → Preview → Confirm → Insert</p></div><strong id="siFormStatus">Draft</strong></div>
      <form id="siForm" class="si-form" novalidate>
        <label>Date<input id="siDate" type="date" required></label>
        <label>Type<select id="siType" required><option value="">Select type</option><option>Production</option><option>Transfer</option><option>Sale</option></select></label>
        <label>Product<select id="siProduct" required></select></label>
        <label>Quantity<input id="siQty" type="number" min="1" step="1" required></label>
        <label id="siFromLabel">From Store<select id="siFrom"></select></label>
        <label id="siToLabel">To Store<select id="siTo"></select></label>
        <label class="si-note">Note<textarea id="siNote" rows="3" placeholder="Optional movement note"></textarea></label>
        <div id="siFormMessage" class="si-form-message" aria-live="polite">Complete the draft, then validate before submission.</div>
        <div class="si-form-actions"><button id="siSave" type="button">Save Draft</button><button id="siValidate" type="button">Validate</button><button id="siPreview" type="button">Preview</button><button id="siSubmit" type="button" disabled>Confirm & Submit Movement</button></div>
      </form>
    </section>
    <section class="si-panel"><div class="si-panel-head"><div><h3>Earlier Movement Ledger Records</h3><p>Movement history is read-only and includes records created before draft linking.</p></div></div>
      <div class="si-filters"><input id="siSearch" type="search" placeholder="Search movements"><input id="siFilterDate" type="date"><select id="siFilterType"><option value="">All types</option><option>Production</option><option>Transfer</option><option>Sale</option></select><select id="siFilterProduct"></select><select id="siFilterStore"></select></div>
      <div class="si-table-wrap si-history-scroll"><table id="siHistory"><thead><tr><th>Date</th><th>Type</th><th>Product</th><th>From</th><th>To</th><th>Qty</th><th>Note</th></tr></thead><tbody></tbody></table></div>
    </section>
  </section>
  <section id="opSummary" class="op-summary"></section><section class="si-panel"><div class="si-panel-head"><h3>Saved Movement Drafts</h3></div><div id="opDrafts" class="op-drafts"></div></section><section class="si-panel"><div class="si-panel-head"><h3>Recent Inventory Insertions</h3></div><div class="op-history-filters"><input data-op-filter="date_from" type="date"><input data-op-filter="date_to" type="date"><select data-op-filter="type"><option value="">All types</option><option>Production</option><option>Transfer</option><option>Sale</option></select><select data-op-filter="product"><option value="">All products</option><option>Sote Phwar 4L</option><option>Sote Phwar 1L</option><option>Sote Phwar 500 mL</option><option>Sote Phwar 100 mL</option></select><select data-op-filter="store"><option value="">All stores</option><option>Factory</option><option>Heho Store (Home)</option><option>Min Hla Store</option><option>Naung Tayar</option><option>Tatkone Store</option></select></div><div id="opHistory" class="op-table"></div><div class="op-paging"><button id="opPrev">Previous</button><span id="opPageInfo"></span><button id="opNext">Next</button><select id="opPageSize"><option>20</option><option>50</option><option>100</option></select></div></section>
</main><dialog id="opRemoveModal" class="op-modal"><h3>Remove Draft</h3><p>Remove this draft? This action removes only the unsubmitted draft. It does not affect any submitted voucher, transaction or inventory record.</p><textarea id="opRemoveReason" placeholder="Optional reason"></textarea><div class="op-actions"><button onclick="this.closest('dialog').close()">Cancel</button><button id="opRemoveConfirm" class="op-remove">Remove Draft</button></div></dialog><dialog id="opDetailModal" class="op-modal"><h3>Submission Details</h3><pre id="opDetailBody"></pre><button onclick="this.closest('dialog').close()">Close</button></dialog><script src="/static/sotephwar_inventory.js?v=20260720-lan1"></script><script src="/static/operational_history.js?v=20260719-1"></script></body></html>'''


def _error(exc):
    if isinstance(exc, sotephwar_inventory.InventoryValidationError):
        return jsonify({"ok": False, "error": "Validation failed", "errors": exc.errors}), 400
    if isinstance(exc, LookupError):
        return jsonify({"ok": False, "error": str(exc)}), 404
    if isinstance(exc, (ValueError, TypeError, RuntimeError)):
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": False, "error": "SotePhwar Inventory operation failed"}), 500


def _protected():
    if request.headers.get("X-Business-OS-Request") not in {API_HEADER, "draft-management-v1"}:
        return jsonify({"ok": False, "error": "Protected Business OS endpoint"}), 403
    return None


def register_sotephwar_inventory(app):
    app.add_url_rule("/business-os/sotephwar-inventory", "business_os_sotephwar_inventory", lambda: PAGE, methods=["GET"])
    api = "/business-os/api/sotephwar-inventory"

    def summary():
        denied = _protected()
        if denied: return denied
        try: return jsonify({"ok": True, "inventory": sotephwar_inventory.inventory_summary()})
        except Exception as exc: return _error(exc)
    app.add_url_rule(f"{api}/summary", "business_os_sotephwar_inventory_summary", summary, methods=["GET"])

    def history():
        denied = _protected()
        if denied: return denied
        try: return jsonify({"ok": True, **sotephwar_inventory.movement_history(request.args)})
        except Exception as exc: return _error(exc)
    app.add_url_rule(f"{api}/movements", "business_os_sotephwar_inventory_history", history, methods=["GET"])

    def validate():
        denied = _protected()
        if denied: return denied
        if not request.is_json: return jsonify({"ok": False, "error": "JSON request required"}), 415
        try: return jsonify({"ok": True, "movement": sotephwar_inventory.validate_movement(request.get_json(silent=True) or {})})
        except Exception as exc: return _error(exc)
    app.add_url_rule(f"{api}/validate", "business_os_sotephwar_inventory_validate", validate, methods=["POST"])

    def submit():
        denied = _protected()
        if denied: return denied
        if not request.is_json: return jsonify({"ok": False, "error": "JSON request required"}), 415
        try: return jsonify({"ok": True, **sotephwar_inventory.submit_movement(request.get_json(silent=True) or {})}), 201
        except Exception as exc: return _error(exc)
    app.add_url_rule(f"{api}/movements", "business_os_sotephwar_inventory_submit", submit, methods=["POST"])

    def drafts():
        denied=_protected()
        if denied:return denied
        try:return jsonify({"ok":True,"drafts":sotephwar_inventory.list_drafts()})
        except Exception as exc:return _error(exc)
    app.add_url_rule(f"{api}/drafts","business_os_sotephwar_inventory_drafts",drafts,methods=["GET"])

    def create_draft():
        denied=_protected()
        if denied:return denied
        try:return jsonify({"ok":True,"draft":sotephwar_inventory.create_draft(request.get_json(silent=True) or {},"Business OS")}),201
        except Exception as exc:return _error(exc)
    app.add_url_rule(f"{api}/drafts","business_os_sotephwar_inventory_create_draft",create_draft,methods=["POST"])

    def get_draft(draft_id):
        denied=_protected()
        if denied:return denied
        try:
            draft=sotephwar_inventory.get_draft(draft_id)
            if not draft:raise LookupError("Inventory movement draft not found")
            return jsonify({"ok":True,"draft":draft})
        except Exception as exc:return _error(exc)
    app.add_url_rule(f"{api}/drafts/<int:draft_id>","business_os_sotephwar_inventory_get_draft",get_draft,methods=["GET"])

    def update_draft(draft_id):
        denied=_protected()
        if denied:return denied
        try:
            body=request.get_json(silent=True) or {}
            return jsonify({"ok":True,"draft":sotephwar_inventory.update_draft(draft_id,body,body.get("version"))})
        except Exception as exc:return _error(exc)
    app.add_url_rule(f"{api}/drafts/<int:draft_id>","business_os_sotephwar_inventory_update_draft",update_draft,methods=["PUT"])

    def draft_state(draft_id,state):
        denied=_protected()
        if denied:return denied
        try:return jsonify({"ok":True,**sotephwar_inventory.set_draft_state(draft_id,state)})
        except Exception as exc:return _error(exc)
    for state in ("validated","previewed"):
        app.add_url_rule(f"{api}/drafts/<int:draft_id>/{state}",f"business_os_sotephwar_inventory_{state}",lambda draft_id,state=state:draft_state(draft_id,state),methods=["POST"])

    def submit_draft(draft_id):
        denied=_protected()
        if denied:return denied
        try:return jsonify({"ok":True,**sotephwar_inventory.submit_draft(draft_id,(request.get_json(silent=True) or {}).get("submission_key"),"Business OS")})
        except Exception as exc:return _error(exc)
    app.add_url_rule(f"{api}/drafts/<int:draft_id>/submit","business_os_sotephwar_inventory_submit_draft",submit_draft,methods=["POST"])

    def remove_draft(draft_id):
        if request.headers.get("X-Business-OS-Request") != "draft-management-v1":return jsonify({"ok":False,"error":"Protected Business OS endpoint"}),403
        try:return jsonify({"ok":True,**sotephwar_inventory.remove_draft(draft_id,"Business OS",(request.get_json(silent=True) or {}).get("reason",""))})
        except Exception as exc:return _error(exc)
    app.add_url_rule(f"{api}/drafts/<int:draft_id>/remove","business_os_sotephwar_inventory_remove_draft",remove_draft,methods=["POST"])

    def recent():
        denied=_protected()
        if denied:return denied
        try:return jsonify({"ok":True,**sotephwar_inventory.recent_insertions(request.args,request.args.get("page",1),request.args.get("page_size",20))})
        except Exception as exc:return _error(exc)
    app.add_url_rule(f"{api}/history","business_os_sotephwar_inventory_recent",recent,methods=["GET"])

    def detail(draft_id):
        denied=_protected()
        if denied:return denied
        try:return jsonify({"ok":True,"submission":sotephwar_inventory.submission_details(draft_id)})
        except Exception as exc:return _error(exc)
    app.add_url_rule(f"{api}/history/<int:draft_id>","business_os_sotephwar_inventory_detail",detail,methods=["GET"])

    def operations():
        denied=_protected()
        if denied:return denied
        try:return jsonify({"ok":True,"summary":sotephwar_inventory.operational_summary()})
        except Exception as exc:return _error(exc)
    app.add_url_rule(f"{api}/operations","business_os_sotephwar_inventory_operations",operations,methods=["GET"])
