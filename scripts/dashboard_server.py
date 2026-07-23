import os
import sys
import tempfile
import secrets
import json
import logging
import requests
from datetime import date, timedelta
from pathlib import Path
from functools import wraps
from hmac import compare_digest
from time import time

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from flask import Flask, Response, jsonify, redirect, request, send_file, session, url_for
from waitress import serve
from werkzeug.exceptions import HTTPException

from tools import dashboard_service
from tools import farm_voucher_repository, voucher_engine
from tools.farm_voucher_pdf import write_farm_voucher_pdf
from tools.bi_reports import write_excel_report
from tools.dashboard_pdf import write_dashboard_pdf
from tools.farm_production_pdf import write_farm_production_excel, write_farm_production_pdf


STATIC_ROOT = PROJECT_ROOT / "dashboard-prototype"
VERSION = "1.0"
logger = logging.getLogger("bigshot.dashboard")
app = Flask(__name__, static_folder=str(STATIC_ROOT), static_url_path="")
app.secret_key = os.getenv("DASHBOARD_SECRET_KEY") or secrets.token_hex(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Strict",
    SESSION_COOKIE_SECURE=os.getenv("DASHBOARD_COOKIE_SECURE", "1") != "0",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=float(os.getenv("DASHBOARD_SESSION_HOURS", "10"))),
)
DEFAULT_HOST = os.getenv("DASHBOARD_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.getenv("DASHBOARD_PORT", "5062"))
MASTER_ROLE = "Admin"
FUTURE_ROLES = ["Manager", "Viewer", "Sales", "Extension", "Accounting", "Inventory", "Admin"]
LOGIN_RATE_LIMIT_MAX_FAILURES = int(os.getenv("DASHBOARD_LOGIN_MAX_FAILURES", "5"))
LOGIN_RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("DASHBOARD_LOGIN_WINDOW_SECONDS", "900"))
PUBLIC_API_PATHS = {"/api/auth/login", "/api/auth/session", "/health", "/ready"}
DASHBOARD_PAGE_PATHS = {
    "/executive",
    "/inventory",
    "/farm-production",
    "/financial",
    "/insights",
    "/farm-voucher",
    "/data-audit",
    "/excel-import",
}


def _voucher_error(exc):
    if isinstance(exc, voucher_engine.VoucherValidationError):
        return jsonify({"ok": False, "error": "Validation failed", "errors": exc.errors}), 400
    if isinstance(exc, (ValueError, RuntimeError)):
        return jsonify({"ok": False, "error": str(exc)}), 400
    if isinstance(exc, LookupError):
        return jsonify({"ok": False, "error": str(exc)}), 404
    app.logger.exception("Farm Voucher operation failed")
    return jsonify({"ok": False, "error": str(exc)}), 500
_FAILED_LOGIN_ATTEMPTS = {}


def _log_event(level, event, **fields):
    payload = {"event": event, **fields}
    logger.log(level, json.dumps(payload, sort_keys=True))


def _client_ip():
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.remote_addr or "unknown"


def _failed_attempts(ip_address):
    cutoff = time() - LOGIN_RATE_LIMIT_WINDOW_SECONDS
    attempts = [attempt for attempt in _FAILED_LOGIN_ATTEMPTS.get(ip_address, []) if attempt >= cutoff]
    _FAILED_LOGIN_ATTEMPTS[ip_address] = attempts
    return attempts


def _rate_limited(ip_address):
    return len(_failed_attempts(ip_address)) >= LOGIN_RATE_LIMIT_MAX_FAILURES


def _record_failed_login(ip_address):
    attempts = _failed_attempts(ip_address)
    attempts.append(time())
    _FAILED_LOGIN_ATTEMPTS[ip_address] = attempts


def _clear_failed_logins(ip_address):
    _FAILED_LOGIN_ATTEMPTS.pop(ip_address, None)


def _auth_configured():
    return bool(os.getenv("MASTER_USERNAME")) and bool(os.getenv("MASTER_PASSWORD"))


def _internal_api_token():
    return os.getenv("DASHBOARD_INTERNAL_API_TOKEN", "")


def _internal_api_configured():
    return bool(_internal_api_token())


def _internal_api_base_url():
    return os.getenv("DASHBOARD_INTERNAL_API_BASE_URL", "").rstrip("/")


def _internal_api_client_enabled():
    return bool(_internal_api_base_url())


def _proxy_internal_dashboard(relative_path):
    token = _internal_api_token()
    if not token:
        _log_event(logging.ERROR, "internal_api_client_not_configured", path=request.path)
        return jsonify({
            "ok": False,
            "error": "Dashboard data service is not configured.",
        }), 503

    upstream_url = f"{_internal_api_base_url()}/{relative_path.lstrip('/')}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": request.headers.get("Accept", "application/json"),
    }
    if request.content_type:
        headers["Content-Type"] = request.content_type

    try:
        upstream = requests.request(
            method=request.method,
            url=upstream_url,
            params=list(request.args.items(multi=True)),
            data=request.get_data() if request.method not in {"GET", "HEAD"} else None,
            headers=headers,
            timeout=(5, float(os.getenv("DASHBOARD_INTERNAL_API_TIMEOUT_SECONDS", "120"))),
            allow_redirects=False,
        )
    except requests.Timeout:
        _log_event(logging.ERROR, "internal_api_timeout", path=request.path)
        return jsonify({
            "ok": False,
            "error": "Dashboard data service timed out.",
        }), 504
    except requests.RequestException as exc:
        _log_event(
            logging.ERROR,
            "internal_api_unavailable",
            path=request.path,
            error_type=type(exc).__name__,
        )
        return jsonify({
            "ok": False,
            "error": "Dashboard data service is unavailable.",
        }), 502

    content = upstream.content
    if relative_path.strip("/") == "executive" and upstream.ok:
        try:
            payload = upstream.json()
            requested = (request.get_json(silent=True) or {}).get("filters", {}).get("period", {})
            if requested.get("type") == "year" and int(requested.get("year") or 0) == date.today().year:
                trend = payload.get("data", {}).get("trend") or []
                month_labels = {date(2000, month, 1).strftime("%b"): month for month in range(1, 13)}
                trend = [row for row in trend if month_labels.get(row.get("label"), 13) <= date.today().month]
                payload["data"]["trend"] = trend
                payload["data"]["latest_trend_period"] = trend[-1].get("label") if trend else None
                content = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        except (TypeError, ValueError, json.JSONDecodeError):
            _log_event(logging.WARNING, "legacy_trend_compatibility_failed", path=request.path)
    response_headers = {}
    for name in ("Content-Type", "Content-Disposition"):
        value = upstream.headers.get(name)
        if value:
            response_headers[name] = value
    _log_event(
        logging.INFO,
        "internal_api_response",
        path=request.path,
        upstream_status=upstream.status_code,
    )
    return Response(content, status=upstream.status_code, headers=response_headers)


def _required_env_status():
    return {
        "MASTER_USERNAME": bool(os.getenv("MASTER_USERNAME")),
        "MASTER_PASSWORD": bool(os.getenv("MASTER_PASSWORD")),
        "DASHBOARD_SECRET_KEY": bool(os.getenv("DASHBOARD_SECRET_KEY")),
    }


def _session_available():
    return bool(app.secret_key) and bool(app.config.get("SESSION_COOKIE_HTTPONLY"))


def _current_user():
    username = session.get("username")
    if not username:
        return None
    return {
        "username": username,
        "role": session.get("role", MASTER_ROLE),
        "future_roles": FUTURE_ROLES,
    }


def _is_authenticated():
    return _current_user() is not None


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not _is_authenticated():
            return jsonify({"ok": False, "error": "Authentication required"}), 401
        return view(*args, **kwargs)
    return wrapped


def internal_api_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        expected_token = _internal_api_token()
        auth_header = request.headers.get("Authorization", "")
        prefix = "Bearer "
        supplied_token = auth_header[len(prefix):] if auth_header.startswith(prefix) else ""
        if not expected_token or not supplied_token or not compare_digest(supplied_token, expected_token):
            _log_event(logging.WARNING, "internal_api_auth_failed", ip=_client_ip(), path=request.path)
            return jsonify({"ok": False, "error": "Internal API authentication required"}), 401
        return view(*args, **kwargs)
    return wrapped


@app.before_request
def require_dashboard_auth():
    if request.path in PUBLIC_API_PATHS or request.path.startswith("/assets/"):
        return None
    if request.path.startswith("/internal/"):
        return None
    if request.path.startswith("/api/dashboard") and not _is_authenticated():
        return jsonify({"ok": False, "error": "Authentication required"}), 401
    if request.path.startswith("/api/data-audit") and not _is_authenticated():
        return jsonify({"ok": False, "error": "Authentication required"}), 401
    if request.path in DASHBOARD_PAGE_PATHS and not _is_authenticated():
        return redirect(url_for("dashboard_page", login="required"))
    return None


@app.after_request
def security_headers(response):
    if request.path.endswith((".js", ".css")) and request.args.get("v"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    elif response.mimetype == "text/html":
        response.headers["Cache-Control"] = "no-cache, max-age=0, must-revalidate"
    else:
        response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; "
        "img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'"
    )
    return response


@app.errorhandler(Exception)
def handle_unexpected_error(error):
    if isinstance(error, HTTPException):
        return error
    _log_event(logging.ERROR, "fatal_error", error_type=type(error).__name__)
    return jsonify({"ok": False, "error": "Internal server error"}), 500


@app.get("/")
def dashboard_page():
    return app.send_static_file("index.html")


@app.get("/executive")
@app.get("/inventory")
@app.get("/farm-production")
@app.get("/financial")
@app.get("/insights")
def dashboard_named_page():
    return app.send_static_file("index.html")

@app.get("/payments")
@app.get("/customers")
def retired_dashboard_page():
    return redirect("/executive")


@app.get("/health")
def health():
    return jsonify({
        "status": "healthy",
        "version": VERSION,
        "authenticated": False,
    })


@app.get("/ready")
def ready():
    env_status = _required_env_status()
    checks = {
        "server": True,
        "environment": all(env_status.values()),
        "session": _session_available(),
    }
    status = "ready" if all(checks.values()) else "not_ready"
    return jsonify({
        "status": status,
        "version": VERSION,
        "checks": checks,
        "required_environment": env_status,
    }), 200 if status == "ready" else 503


@app.get("/api/auth/session")
def auth_session():
    return jsonify({
        "ok": True,
        "authenticated": _is_authenticated(),
        "user": _current_user(),
        "auth_configured": _auth_configured(),
    })


@app.post("/api/auth/login")
def auth_login():
    if not _auth_configured():
        return jsonify({
            "ok": False,
            "error": "Dashboard master credentials are not configured.",
        }), 503
    ip_address = _client_ip()
    if _rate_limited(ip_address):
        _log_event(logging.WARNING, "login_rate_limited", ip=ip_address)
        return jsonify({
            "ok": False,
            "error": "Too many failed login attempts. Try again later.",
        }), 429
    payload = request.get_json(silent=True) or {}
    username = str(payload.get("username") or "")
    password = str(payload.get("password") or "")
    valid_username = compare_digest(username, os.getenv("MASTER_USERNAME", ""))
    valid_password = compare_digest(password, os.getenv("MASTER_PASSWORD", ""))
    if not valid_username or not valid_password:
        session.clear()
        _record_failed_login(ip_address)
        _log_event(logging.WARNING, "login_failed", ip=ip_address, username=username)
        return jsonify({"ok": False, "error": "Invalid username or password."}), 401
    session.clear()
    session.permanent = True
    session["username"] = username
    session["role"] = MASTER_ROLE
    _clear_failed_logins(ip_address)
    _log_event(logging.INFO, "login_success", ip=ip_address, username=username, role=MASTER_ROLE)
    return jsonify({"ok": True, "user": _current_user()})


@app.post("/api/auth/logout")
def auth_logout():
    username = session.get("username")
    _log_event(logging.INFO, "logout", ip=_client_ip(), username=username)
    session.clear()
    return jsonify({"ok": True})


@app.get("/api/dashboard/meta")
@login_required
def dashboard_meta():
    return jsonify({
        "ok": True,
        "read_only": True,
        "business_logic": "canonical_bi_engine",
        "milestone": 1,
        "pages": ["executive", "inventory", "farm-production", "financial", "insights"],
        "executive_read_only": True,
        "write_modules": [],
        "roles_ready": FUTURE_ROLES,
    })


@app.get("/api/dashboard/dimensions")
@login_required
def dimensions():
    if _internal_api_client_enabled():
        return _proxy_internal_dashboard("dimensions")
    try:
        return jsonify({"ok": True, "data": dashboard_service.dashboard_dimensions()})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


def _filters_from_request():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ValueError("JSON body is required")
    return dashboard_service.parse_dashboard_filters(payload)


def _executive_dashboard_response():
    filters = _filters_from_request()
    refresh = bool((request.get_json(silent=True) or {}).get("refresh"))
    if refresh:
        dashboard_service.clear_dashboard_cache()
    data, cached = dashboard_service.executive_dashboard(filters)
    return jsonify({
        "ok": True,
        "cached": cached,
        "data": data,
    })


def _executive_insight_response():
    filters = _filters_from_request()
    data, cached = dashboard_service.executive_insight(filters)
    return jsonify({"ok": True, "cached": cached, "data": data})


def _farm_production_response():
    filters = dashboard_service.parse_farm_production_filters(request.get_json(silent=True))
    return jsonify({"ok": True, "data": dashboard_service.farm_production_dashboard(filters)})

def _farm_production_pdf_response():
    filters = dashboard_service.parse_farm_production_filters(request.get_json(silent=True))
    data = dashboard_service.farm_production_dashboard(filters)
    handle = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    path = Path(handle.name)
    handle.close()
    write_farm_production_pdf(data, path)
    return send_file(
        path,
        as_attachment=True,
        download_name="BigShot_Farm_Production.pdf",
        mimetype="application/pdf",
    )


def _farm_production_excel_response():
    filters = dashboard_service.parse_farm_production_filters(request.get_json(silent=True))
    data = dashboard_service.farm_production_dashboard(filters)
    handle = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
    path = Path(handle.name)
    handle.close()
    write_farm_production_excel(data, path)
    return send_file(
        path,
        as_attachment=True,
        download_name="BigShot_Farm_Production.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def _inventory_response():
    return jsonify({"ok": True, "data": dashboard_service.inventory_dashboard(
        year=request.args.get("year"), month=request.args.get("month"),
    )})
def _payments_response():
    filters = _filters_from_request()
    return jsonify({"ok": True, "data": dashboard_service.payments_dashboard(filters)})


@app.post("/api/dashboard/executive")
@login_required
def executive_dashboard():
    if _internal_api_client_enabled():
        return _proxy_internal_dashboard("executive")
    try:
        return _executive_dashboard_response()
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        app.logger.exception("Executive dashboard failed")
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.post("/api/dashboard/insights/executive")
@login_required
def executive_insight():
    if _internal_api_client_enabled():
        return _proxy_internal_dashboard("insights/executive")
    try:
        return _executive_insight_response()
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        app.logger.exception("Executive insight failed")
        return jsonify({
            "ok": False,
            "error": "Executive narrative is temporarily unavailable.",
            "detail": str(exc),
        }), 503


@app.post("/api/dashboard/farm-production")
@login_required
def farm_production_dashboard():
    if _internal_api_client_enabled():
        return _proxy_internal_dashboard("farm-production")
    try:
        return _farm_production_response()
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        app.logger.exception("Farm Production dashboard failed")
        return jsonify({"ok": False, "error": str(exc)}), 500

@app.post("/api/dashboard/farm-production/export/pdf")
@login_required
def farm_production_pdf():
    if _internal_api_client_enabled():
        return _proxy_internal_dashboard("farm-production/export/pdf")
    try:
        return _farm_production_pdf_response()
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        app.logger.exception("Farm Production PDF failed")
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.post("/api/dashboard/farm-production/export/excel")
@login_required
def farm_production_excel():
    if _internal_api_client_enabled():
        return _proxy_internal_dashboard("farm-production/export/excel")
    try:
        return _farm_production_excel_response()
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        app.logger.exception("Farm Production Excel failed")
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.get("/api/dashboard/inventory")
@login_required
def inventory_dashboard():
    if _internal_api_client_enabled():
        return _proxy_internal_dashboard("inventory")
    try:
        return _inventory_response()
    except Exception as exc:
        app.logger.exception("Inventory dashboard failed")
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.post("/api/dashboard/payments")
@login_required
def payments_dashboard():
    if _internal_api_client_enabled():
        return _proxy_internal_dashboard("payments")
    try:
        return _payments_response()
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        app.logger.exception("Payments dashboard failed")
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.get("/api/vouchers/farm/customers")
@login_required
def farm_voucher_customers():
    try:
        return jsonify({"ok": True, "customers": farm_voucher_repository.list_customers()})
    except Exception as exc:
        return _voucher_error(exc)


@app.get("/api/vouchers/farm/crops")
@login_required
def farm_voucher_crops():
    try:
        return jsonify({"ok": True, "crops": farm_voucher_repository.list_crops()})
    except Exception as exc:
        return _voucher_error(exc)


@app.get("/api/vouchers/farm/drafts")
@login_required
def farm_voucher_drafts():
    try:
        return jsonify({"ok": True, "drafts": farm_voucher_repository.list_drafts()})
    except Exception as exc:
        return _voucher_error(exc)


@app.post("/api/vouchers/farm/drafts")
@login_required
def create_farm_voucher_draft():
    try:
        draft = farm_voucher_repository.create_draft(request.get_json(silent=True) or {}, _current_user()["username"])
        return jsonify({"ok": True, "draft": draft}), 201
    except Exception as exc:
        return _voucher_error(exc)


@app.get("/api/vouchers/farm/drafts/<int:draft_id>")
@login_required
def get_farm_voucher_draft(draft_id):
    try:
        draft = farm_voucher_repository.get_draft(draft_id)
        if not draft:
            raise LookupError("Farm voucher draft not found")
        return jsonify({"ok": True, "draft": draft})
    except Exception as exc:
        return _voucher_error(exc)


@app.put("/api/vouchers/farm/drafts/<int:draft_id>")
@login_required
def update_farm_voucher_draft(draft_id):
    try:
        body = request.get_json(silent=True) or {}
        draft = farm_voucher_repository.update_draft(draft_id, body, body.get("version"))
        return jsonify({"ok": True, "draft": draft})
    except Exception as exc:
        return _voucher_error(exc)


@app.post("/api/vouchers/farm/drafts/<int:draft_id>/validate")
@login_required
def validate_farm_voucher_draft(draft_id):
    try:
        return jsonify({"ok": True, **farm_voucher_repository.set_workflow_state(draft_id, "validated")})
    except Exception as exc:
        return _voucher_error(exc)


@app.post("/api/vouchers/farm/drafts/<int:draft_id>/preview")
@login_required
def preview_farm_voucher_draft(draft_id):
    try:
        return jsonify({"ok": True, **farm_voucher_repository.set_workflow_state(draft_id, "previewed")})
    except Exception as exc:
        return _voucher_error(exc)


@app.get("/api/vouchers/farm/drafts/<int:draft_id>/pdf")
@login_required
def farm_voucher_pdf(draft_id):
    try:
        draft = farm_voucher_repository.get_draft(draft_id)
        if not draft:
            raise LookupError("Farm voucher draft not found")
        voucher = voucher_engine.preview(draft)
        handle = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        path = Path(handle.name)
        handle.close()
        write_farm_voucher_pdf(voucher, path)
        return send_file(path, as_attachment=True, download_name=f'Farm_Voucher_{voucher["voucher_number"]}.pdf', mimetype="application/pdf")
    except Exception as exc:
        return _voucher_error(exc)


@app.post("/api/vouchers/farm/drafts/<int:draft_id>/submit")
@login_required
def submit_farm_voucher_draft(draft_id):
    try:
        result = farm_voucher_repository.submit(draft_id, _current_user()["username"])
        dashboard_service.clear_dashboard_cache()
        return jsonify({"ok": True, **result})
    except Exception as exc:
        return _voucher_error(exc)


def _export_payload(filters):
    data, _ = dashboard_service.executive_dashboard(filters)
    result = {
        "formula": "kpi_overview",
        "period": dashboard_service.legacy_period(filters.period),
        "total_income": data["metrics"]["revenue"],
        "total_expense": data["metrics"]["expenses"],
        "net_profit": data["metrics"]["net_profit"],
        "profit_margin_percent": data["metrics"]["profit_margin_percent"],
        "amount_received": data["metrics"]["cash_received"],
        "outstanding_amount": data["metrics"]["outstanding_receivables"],
        "sources": data["sources"],
    }
    return {
        "intent": {"business": "executive", "module": "kpi", "report": "kpi"},
        "title": "BigShot Executive Dashboard",
        "period_label": data["filter_label"],
        "result": result,
    }


def _export_excel_response():
    filters = _filters_from_request()
    handle = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
    path = Path(handle.name)
    handle.close()
    write_excel_report(_export_payload(filters), path)
    return send_file(
        path,
        as_attachment=True,
        download_name="BigShot_Executive_Dashboard.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def _export_pdf_response():
    filters = _filters_from_request()
    data, _ = dashboard_service.executive_dashboard(filters)
    handle = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    path = Path(handle.name)
    handle.close()
    write_dashboard_pdf(data, path)
    return send_file(
        path,
        as_attachment=True,
        download_name="BigShot_Executive_Dashboard.pdf",
        mimetype="application/pdf",
    )


@app.post("/api/dashboard/export/excel")
@login_required
def export_excel():
    if _internal_api_client_enabled():
        return _proxy_internal_dashboard("export/excel")
    try:
        return _export_excel_response()
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.post("/api/dashboard/export/pdf")
@login_required
def export_pdf():
    if _internal_api_client_enabled():
        return _proxy_internal_dashboard("export/pdf")
    try:
        return _export_pdf_response()
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.get("/internal/v1/dashboard/dimensions")
@internal_api_required
def internal_v1_dimensions():
    if _internal_api_client_enabled():
        return _proxy_internal_dashboard("dimensions")
    try:
        return jsonify({"ok": True, "data": dashboard_service.dashboard_dimensions()})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.get("/internal/v1/dashboard/health")
@internal_api_required
def internal_v1_health():
    return jsonify({
        "ok": True,
        "status": "healthy",
        "version": VERSION,
    })


@app.post("/internal/v1/dashboard/executive")
@internal_api_required
def internal_v1_executive_dashboard():
    if _internal_api_client_enabled():
        return _proxy_internal_dashboard("executive")
    try:
        return _executive_dashboard_response()
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        app.logger.exception("Internal executive dashboard failed")
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.post("/internal/v1/dashboard/insights/executive")
@internal_api_required
def internal_v1_executive_insight():
    if _internal_api_client_enabled():
        return _proxy_internal_dashboard("insights/executive")
    try:
        return _executive_insight_response()
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        app.logger.exception("Internal executive insight failed")
        return jsonify({
            "ok": False,
            "error": "Executive narrative is temporarily unavailable.",
            "detail": str(exc),
        }), 503


@app.post("/internal/v1/dashboard/farm-production")
@internal_api_required
def internal_v1_farm_production():
    if _internal_api_client_enabled():
        return _proxy_internal_dashboard("farm-production")
    try:
        return _farm_production_response()
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500

@app.post("/internal/v1/dashboard/farm-production/export/pdf")
@internal_api_required
def internal_v1_farm_production_pdf():
    if _internal_api_client_enabled():
        return _proxy_internal_dashboard("farm-production/export/pdf")
    try:
        return _farm_production_pdf_response()
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.post("/internal/v1/dashboard/farm-production/export/excel")
@internal_api_required
def internal_v1_farm_production_excel():
    if _internal_api_client_enabled():
        return _proxy_internal_dashboard("farm-production/export/excel")
    try:
        return _farm_production_excel_response()
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.get("/internal/v1/dashboard/inventory")
@internal_api_required
def internal_v1_inventory():
    if _internal_api_client_enabled():
        return _proxy_internal_dashboard("inventory")
    try:
        return _inventory_response()
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.post("/internal/v1/dashboard/payments")
@internal_api_required
def internal_v1_payments_dashboard():
    if _internal_api_client_enabled():
        return _proxy_internal_dashboard("payments")
    try:
        return _payments_response()
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.post("/internal/v1/dashboard/export/excel")
@internal_api_required
def internal_v1_export_excel():
    if _internal_api_client_enabled():
        return _proxy_internal_dashboard("export/excel")
    try:
        return _export_excel_response()
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.post("/internal/v1/dashboard/export/pdf")
@internal_api_required
def internal_v1_export_pdf():
    if _internal_api_client_enabled():
        return _proxy_internal_dashboard("export/pdf")
    try:
        return _export_pdf_response()
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


from tools.data_audit_portal import register_data_audit

register_data_audit(app, login_required, _current_user)


if __name__ == "__main__":
    logging.basicConfig(level=os.getenv("DASHBOARD_LOG_LEVEL", "INFO"))
    _log_event(logging.INFO, "server_startup", host=DEFAULT_HOST, port=DEFAULT_PORT, version=VERSION)
    serve(app, host=DEFAULT_HOST, port=DEFAULT_PORT, threads=8)
