import os
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from flask import Flask, jsonify, request, send_file
from waitress import serve

from tools import dashboard_service
from tools.bi_reports import write_excel_report
from tools.chart_pdf import create_chart_pdf_report_from_result


STATIC_ROOT = PROJECT_ROOT / "dashboard-prototype"
app = Flask(__name__, static_folder=str(STATIC_ROOT), static_url_path="")
DEFAULT_HOST = os.getenv("DASHBOARD_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.getenv("DASHBOARD_PORT", "5062"))


@app.after_request
def security_headers(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; "
        "img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'"
    )
    return response


@app.get("/")
def dashboard_page():
    return app.send_static_file("index.html")


@app.get("/health")
def health():
    return jsonify({"ok": True, "service": "bigshot-business-dashboard", "read_only": True})


@app.get("/api/dashboard/meta")
def dashboard_meta():
    return jsonify({
        "ok": True,
        "read_only": True,
        "business_logic": "canonical_bi_engine",
        "milestone": 1,
        "pages": ["executive"],
    })


@app.get("/api/dashboard/dimensions")
def dimensions():
    try:
        return jsonify({"ok": True, "data": dashboard_service.dashboard_dimensions()})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


def _filters_from_request():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ValueError("JSON body is required")
    return dashboard_service.parse_dashboard_filters(payload)


@app.post("/api/dashboard/executive")
def executive_dashboard():
    try:
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
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        app.logger.exception("Executive dashboard failed")
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.post("/api/dashboard/insights/executive")
def executive_insight():
    try:
        filters = _filters_from_request()
        data, cached = dashboard_service.executive_insight(filters)
        return jsonify({"ok": True, "cached": cached, "data": data})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        app.logger.exception("Executive insight failed")
        return jsonify({
            "ok": False,
            "error": "Executive narrative is temporarily unavailable.",
            "detail": str(exc),
        }), 503


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


@app.post("/api/dashboard/export/excel")
def export_excel():
    try:
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
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.post("/api/dashboard/export/pdf")
def export_pdf():
    try:
        filters = _filters_from_request()
        payload = _export_payload(filters)
        handle = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        path = Path(handle.name)
        handle.close()
        create_chart_pdf_report_from_result(
            payload["result"],
            f"Executive dashboard · {payload['period_label']}",
            path,
            title=payload["title"],
        )
        return send_file(
            path,
            as_attachment=True,
            download_name="BigShot_Executive_Dashboard.pdf",
            mimetype="application/pdf",
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


if __name__ == "__main__":
    serve(app, host=DEFAULT_HOST, port=DEFAULT_PORT, threads=8)
