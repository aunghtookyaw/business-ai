"""Customer Master page and JSON API for Business OS data-entry staff."""

from flask import jsonify, request

from tools import customer_master

PROTECTED = "customer-master-v1"


def _protected():
    return request.headers.get("X-Business-OS-Request") == PROTECTED


def _is_admin():
    # Reserved for a trusted upstream authenticator; the current Business OS
    # service does not set this value, so standard LAN users are data-entry staff.
    return request.environ.get("business_os.role") == "administrator"


def _error(exc):
    known = isinstance(exc, customer_master.CustomerError)
    body = {"ok": False, "error": str(exc) if known else "Customer operation could not be completed",
            "code": getattr(exc, "code", "database_failure") if known else "database_failure"}
    if isinstance(exc, customer_master.DuplicateWarning): body["matches"] = exc.matches
    return jsonify(body), getattr(exc, "status_code", 500) if known else 500


PAGE = '''<link rel="stylesheet" href="/static/customer_master.css">
<main class="cm-app">
 <section class="cm-head"><div><span>Master Data</span><h2>Customer Master</h2><p>Maintain customer contact and voucher eligibility without changing historical records.</p></div><button id="cmAdd" class="cm-primary">Add Customer</button></section>
 <section id="cmSummary" class="cm-summary" aria-label="Customer counts"></section>
 <section class="cm-panel"><div class="cm-quick" id="cmQuick"><button data-qf="all" class="active">All Customers</button><button data-qf="Farm">Farm</button><button data-qf="SotePhwar">SotePhwar</button><button data-qf="Both">Both</button><button data-qf="inactive">Inactive</button><button data-qf="recent">Recently Added</button></div>
  <div class="cm-filters"><input id="cmSearch" type="search" placeholder="Search name, phone, town or address"><input id="cmPhone" placeholder="Phone"><input id="cmTown" placeholder="Town"><select id="cmGroup"><option value="">All groups</option><option>Farm</option><option>SotePhwar</option><option>Both</option></select><select id="cmActive"><option value="">Active and inactive</option><option value="true">Active</option><option value="false">Inactive</option></select><button id="cmFilter">Search</button></div>
  <div id="cmMessage" class="cm-message" hidden></div><div id="cmList" class="cm-list" aria-live="polite"></div><div class="cm-pages"><button id="cmPrev">Previous</button><span id="cmPage"></span><button id="cmNext">Next</button><select id="cmPageSize"><option>20</option><option>50</option><option>100</option></select></div>
 </section>
</main>
<dialog id="cmFormDialog" class="cm-dialog"><form id="cmForm"><header><h3 id="cmFormTitle">Add Customer</h3><button type="button" data-close>Close</button></header><input id="cmId" type="hidden"><input id="cmVersion" type="hidden"><div class="cm-form-grid"><label>Customer name *<input id="cmName" required></label><label>Customer group *<select id="cmFormGroup" required><option value="">Select</option><option>Farm</option><option>SotePhwar</option><option>Both</option></select></label><label>Phone number<input id="cmFormPhone" inputmode="tel"></label><label>Town<input id="cmFormTown"></label><label>Payment terms days<input id="cmTerms" type="number" min="0" max="3650" value="0"></label><label class="cm-wide">Contact address<textarea id="cmAddress"></textarea></label><label class="cm-wide">Notes<textarea id="cmNotes"></textarea></label></div><div id="cmFormError" class="cm-message" hidden></div><footer><button type="button" data-close>Cancel</button><button class="cm-primary" type="submit">Save Customer</button></footer></form></dialog>
<dialog id="cmDuplicateDialog" class="cm-dialog"><header><h3>Possible duplicate customer</h3></header><p>Review these existing customers before creating another record.</p><div id="cmDuplicates"></div><footer><button id="cmDuplicateCancel">Cancel</button></footer></dialog>
<dialog id="cmDetailDialog" class="cm-dialog cm-detail"><header><h3>Customer Details</h3><button type="button" data-close>Close</button></header><div id="cmDetail"></div></dialog>
<script src="/static/customer_master.js?v=20260719-1"></script>'''


def register_customer_master(app):
    api = "/business-os/api/customers"

    app.add_url_rule("/business-os/customers", "business_os_customers", lambda: PAGE, methods=["GET"])

    @app.get(api)
    def customers_list():
        try: return jsonify({"ok": True, **customer_master.list_customers(request.args, request.args.get("page", 1), request.args.get("page_size", 20))})
        except Exception as exc: return _error(exc)

    @app.get(f"{api}/summary")
    def customers_summary():
        try: return jsonify({"ok": True, "summary": customer_master.summary()})
        except Exception as exc: return _error(exc)

    @app.get(f"{api}/<int:customer_id>")
    def customer_detail(customer_id):
        try: return jsonify({"ok": True, **customer_master.customer_detail(customer_id)})
        except Exception as exc: return _error(exc)

    @app.post(f"{api}/submission-key")
    def customer_submission_key():
        if not _protected(): return jsonify({"ok": False, "code": "forbidden", "error": "Protected Customer Master endpoint"}), 403
        return jsonify({"ok": True, "submission_key": customer_master.new_submission_key()})

    @app.post(f"{api}/duplicates")
    def customer_duplicates():
        if not _protected(): return jsonify({"ok": False, "code": "forbidden", "error": "Protected Customer Master endpoint"}), 403
        try: return jsonify({"ok": True, "matches": customer_master.duplicate_matches(request.get_json(silent=True) or {})})
        except Exception as exc: return _error(exc)

    @app.post(api)
    def customer_create():
        if not _protected(): return jsonify({"ok": False, "code": "forbidden", "error": "Protected Customer Master endpoint"}), 403
        body = request.get_json(silent=True) or {}
        try:
            allow = bool(body.get("continue_duplicate")) and _is_admin()
            return jsonify({"ok": True, "customer": customer_master.create_customer(body, body.get("submission_key"), allow_duplicate=allow)})
        except Exception as exc: return _error(exc)

    @app.put(f"{api}/<int:customer_id>")
    def customer_update(customer_id):
        if not _protected(): return jsonify({"ok": False, "code": "forbidden", "error": "Protected Customer Master endpoint"}), 403
        body = request.get_json(silent=True) or {}
        try: return jsonify({"ok": True, "customer": customer_master.update_customer(customer_id, body, body.get("expected_version"), body.get("submission_key"))})
        except Exception as exc: return _error(exc)

    @app.post(f"{api}/<int:customer_id>/status")
    def customer_status(customer_id):
        if not _protected(): return jsonify({"ok": False, "code": "forbidden", "error": "Protected Customer Master endpoint"}), 403
        if not _is_admin(): return jsonify({"ok": False, "code": "administrator_required", "error": "Administrator authorization is required"}), 403
        body = request.get_json(silent=True) or {}
        try: return jsonify({"ok": True, "customer": customer_master.set_active(customer_id, body.get("active"), body.get("expected_version"), body.get("submission_key"), "administrator")})
        except Exception as exc: return _error(exc)
