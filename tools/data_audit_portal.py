"""Authenticated Flask routes for the BigShot Data Audit Center."""

from __future__ import annotations

import tempfile
from pathlib import Path

from flask import Response, jsonify, request, send_file

from tools import data_audit


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Data Audit Center · BigShot Business OS</title>
<link rel="stylesheet" href="/styles.css?v=20260723-farm-summary1">
<link rel="stylesheet" href="/data-audit.css?v=20260723-1"></head>
<body class="da-body"><div class="app-shell da-shell">
<aside class="sidebar open"><a class="brand" href="/"><span class="brand-mark"><img src="/assets/bigshot-logo.jpg" alt=""></span><span><strong>BIGSHOT</strong><small>Business Intelligence</small></span></a>
<nav class="primary-nav"><a class="nav-item" href="/executive">⌂ <span>Executive</span></a><a class="nav-item" href="/inventory">□ <span>Inventory</span></a><p class="da-nav-heading">Admin</p><a class="nav-item active" href="/data-audit">✓ <span>Data Audit</span></a></nav>
<div class="sidebar-footer"><a class="nav-item" href="/">Back to Dashboard</a></div></aside>
<main class="main da-main"><header class="da-topbar"><div><p class="eyebrow">ADMIN · DATA QUALITY</p><h1>Data Audit Center</h1><p>Upload, compare, review and safely apply approved Excel differences.</p></div><a class="button secondary" href="/">Dashboard</a></header>
<nav class="da-workflow" aria-label="Data audit workflow"><button data-view="upload" class="active">Upload Excel</button><button data-view="audit">Run Audit</button><button data-view="review">Review Differences</button><button data-view="apply">Apply Changes</button><button data-view="history">Audit History</button><button data-view="customer-alias">Customer Aliases</button><button data-view="product-alias">Product Aliases</button></nav>
<div id="daNotice" class="da-notice" hidden></div>
<section id="daUpload" class="da-view">
 <div class="da-panel"><h2>1. Upload Excel</h2><form id="daUploadForm"><div class="da-form-grid"><label>Target table<select name="target_key" required><option value="sotephwar_transection">SotePhwar Transaction</option><option value="farm_transection">Farm Transaction</option><option value="transection">General Transaction</option></select></label><label>Excel or CSV file<input name="file" type="file" accept=".xlsx,.xls,.csv" required></label></div><button class="button primary">Upload and inspect</button></form></div>
 <div id="daFileProfile" class="da-panel" hidden></div><div id="daMapping" class="da-panel" hidden></div>
</section>
<section id="daAudit" class="da-view" hidden><div class="da-panel"><h2>2. Read-only Audit</h2><p>Comparison does not modify production records.</p><button id="daRunAudit" class="button primary" disabled>Run read-only audit</button></div><div id="daKpis" class="da-kpis"></div></section>
<section id="daReview" class="da-view" hidden>
 <div class="da-panel"><div class="da-panel-head"><div><h2>3. Review Differences</h2><p>Nothing changes until an administrator applies approved rows.</p></div><div class="da-exports"><a id="daExportAll" class="button secondary">Audit CSV</a><a id="daExportMismatch" class="button secondary">Mismatch CSV</a><a id="daExportPdf" class="button secondary">Summary PDF</a></div></div>
 <div class="da-tabs" id="daTabs"><button data-classification="excel_only">Safe New</button><button data-classification="voucher_exact_match">Exact</button><button data-classification="voucher_normalized_match">Normalized</button><button data-classification="amount_mismatch">Amount</button><button data-classification="quantity_mismatch">Quantity</button><button data-classification="database_only">Database Only</button><button data-classification="ambiguous">Ambiguous</button><button data-classification="probable_duplicate">Duplicates</button></div>
 <div class="da-table-tools"><input id="daSearch" type="search" placeholder="Search voucher, customer, product…"><select id="daDecisionFilter"><option value="">All decisions</option><option>pending</option><option>accept_excel</option><option>accept_database</option><option>ignore</option><option>merge_alias</option></select><button id="daExportVisible" class="button secondary">Export</button></div>
 <div class="da-table-wrap"><table><thead><tr><th></th><th><button class="da-sort" data-sort="classification">Type</button></th><th><button class="da-sort" data-sort="excel_row_number">Voucher / Date</button></th><th>Customer / Product</th><th>Excel</th><th>Database</th><th>Difference</th><th>Action</th></tr></thead><tbody id="daRows"></tbody></table></div><div id="daPager" class="da-pager"></div></div>
</section>
<section id="daApply" class="da-view" hidden><div class="da-panel"><h2>4. Apply Approved Changes</h2><div class="da-warning"><strong>Administrator only.</strong> Affected records are backed up and all changes use one PostgreSQL transaction. Any failure rolls back everything.</div><button id="daApplyButton" class="button danger" disabled>Apply approved Excel changes</button><a id="daChangeLog" class="button secondary" hidden>Download Change Log</a></div></section>
<section id="daHistory" class="da-view" hidden><div class="da-panel"><h2>Audit History</h2><div class="da-table-wrap"><table><thead><tr><th>Audit</th><th>Date</th><th>User</th><th>Target</th><th>File</th><th>Compared</th><th>Applied</th><th>Status</th><th></th></tr></thead><tbody id="daHistoryRows"></tbody></table></div></div></section>
<section id="daCustomerAlias" class="da-view" hidden><div class="da-panel"><h2>Customer Alias Manager</h2><div id="daCustomerAliasEditor"></div><div id="daCustomerAliases"></div></div></section>
<section id="daProductAlias" class="da-view" hidden><div class="da-panel"><h2>Product Alias Manager</h2><div id="daProductAliasEditor"></div><div id="daProductAliases"></div></div></section>
<dialog id="daDetails"><form method="dialog"><button class="da-close">Close</button><h2>Difference details</h2><pre id="daDetailContent"></pre></form></dialog>
</main></div><script src="/data-audit.js?v=20260723-1"></script></body></html>"""


def _error(exc):
    if isinstance(exc, PermissionError):
        return jsonify({"ok": False, "code": "forbidden", "error": str(exc)}), 403
    if isinstance(exc, LookupError):
        return jsonify({"ok": False, "error": str(exc)}), 404
    if isinstance(exc, (ValueError, RuntimeError)):
        return jsonify({"ok": False, "error": str(exc)}), 400
    return jsonify({"ok": False, "error": "Data Audit operation failed."}), 500


def register_data_audit(app, login_required, current_user):
    def user():
        return (current_user() or {}).get("username") or "unknown"

    def owned_audit(audit_id):
        if (current_user() or {}).get("role") == "Admin":
            return None
        audit = data_audit.get_audit(audit_id)
        if audit.get("created_by") != user():
            raise PermissionError("This audit session belongs to another user.")
        return audit

    def admin_required(view):
        @login_required
        def wrapped(*args, **kwargs):
            if (current_user() or {}).get("role") != "Admin":
                return jsonify({"ok": False, "code": "administrator_required", "error": "Administrator permission is required."}), 403
            return view(*args, **kwargs)
        wrapped.__name__ = f"data_audit_admin_{view.__name__}"
        return wrapped

    app.add_url_rule("/data-audit", "data_audit_page", login_required(lambda: Response(PAGE, content_type="text/html; charset=utf-8")), methods=["GET"])
    app.add_url_rule("/excel-import", "authenticated_excel_import_page", login_required(lambda: Response(PAGE, content_type="text/html; charset=utf-8")), methods=["GET"])

    @app.post("/api/data-audit/upload")
    @login_required
    def data_audit_upload():
        upload = request.files.get("file")
        if upload is None or not upload.filename:
            return jsonify({"ok": False, "error": "Choose an Excel or CSV file."}), 400
        try:
            return jsonify({"ok": True, "audit": data_audit.upload_audit(upload, request.form.get("target_key", ""), user())})
        except Exception as exc:
            return _error(exc)

    @app.put("/api/data-audit/<int:audit_id>/mapping")
    @login_required
    def data_audit_mapping(audit_id):
        body = request.get_json(silent=True) or {}
        try:
            owned_audit(audit_id)
            return jsonify({"ok": True, "audit": data_audit.save_mapping(audit_id, body.get("mapping") or {}, user(), body.get("template_name") or "")})
        except Exception as exc:
            return _error(exc)

    @app.post("/api/data-audit/<int:audit_id>/run")
    @login_required
    def data_audit_run(audit_id):
        try:
            owned_audit(audit_id)
            return jsonify({"ok": True, "audit": data_audit.run_audit(audit_id, user())})
        except Exception as exc:
            return _error(exc)

    @app.get("/api/data-audit/<int:audit_id>")
    @login_required
    def data_audit_detail(audit_id):
        try:
            owned_audit(audit_id)
            return jsonify({"ok": True, "audit": data_audit.get_audit(audit_id)})
        except Exception as exc:
            return _error(exc)

    @app.get("/api/data-audit/<int:audit_id>/differences")
    @login_required
    def data_audit_differences(audit_id):
        try:
            owned_audit(audit_id)
            return jsonify({"ok": True, **data_audit.list_differences(audit_id, request.args)})
        except Exception as exc:
            return _error(exc)

    @app.post("/api/data-audit/<int:audit_id>/decisions")
    @login_required
    def data_audit_decisions(audit_id):
        body = request.get_json(silent=True) or {}
        if body.get("decision") == "merge_alias" and (current_user() or {}).get("role") != "Admin":
            return jsonify({"ok": False, "code": "administrator_required", "error": "Administrator permission is required to manage aliases."}), 403
        try:
            owned_audit(audit_id)
            return jsonify({"ok": True, **data_audit.decide(audit_id, body.get("row_ids") or [], body.get("decision"), body.get("note"), user())})
        except Exception as exc:
            return _error(exc)

    @app.post("/api/data-audit/<int:audit_id>/apply")
    @admin_required
    def data_audit_apply(audit_id):
        try:
            owned_audit(audit_id)
            return jsonify({"ok": True, **data_audit.apply_audit(audit_id, user())})
        except Exception as exc:
            return _error(exc)

    @app.get("/api/data-audit/history")
    @login_required
    def data_audit_history():
        try:
            return jsonify({"ok": True, **data_audit.list_history(request.args)})
        except Exception as exc:
            return _error(exc)

    @app.delete("/api/data-audit/<int:audit_id>")
    @admin_required
    def data_audit_delete(audit_id):
        try:
            return jsonify({"ok": True, **data_audit.delete_audit(audit_id)})
        except Exception as exc:
            return _error(exc)

    @app.get("/api/data-audit/aliases")
    @login_required
    def data_audit_aliases():
        try:
            return jsonify({"ok": True, "aliases": data_audit.list_aliases(request.args.get("type", ""), request.args.get("search", ""))})
        except Exception as exc:
            return _error(exc)

    @app.post("/api/data-audit/aliases")
    @admin_required
    def data_audit_alias_create():
        try:
            return jsonify({"ok": True, "alias": data_audit.save_alias(None, request.get_json(silent=True) or {}, user())})
        except Exception as exc:
            return _error(exc)

    @app.put("/api/data-audit/aliases/<int:alias_id>")
    @admin_required
    def data_audit_alias_update(alias_id):
        try:
            return jsonify({"ok": True, "alias": data_audit.save_alias(alias_id, request.get_json(silent=True) or {}, user())})
        except Exception as exc:
            return _error(exc)

    @app.get("/api/data-audit/<int:audit_id>/export/<kind>")
    @login_required
    def data_audit_export(audit_id, kind):
        owned_audit(audit_id)
        if kind in {"csv", "mismatch"}:
            body = data_audit.export_csv(audit_id, "mismatch" if kind == "mismatch" else "all")
            filename = f"Data_Audit_{audit_id}_{kind}.csv"
            return Response(body, content_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{filename}"'})
        if kind == "changes":
            body = data_audit.export_change_log(audit_id)
            return Response(body, content_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="Data_Audit_{audit_id}_Change_Log.csv"'})
        if kind == "pdf":
            handle = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
            path = Path(handle.name)
            handle.close()
            data_audit.export_summary_pdf(audit_id, path)
            return send_file(path, as_attachment=True, download_name=f"Data_Audit_{audit_id}_Summary.pdf", mimetype="application/pdf")
        return jsonify({"ok": False, "error": "Unsupported export."}), 404
