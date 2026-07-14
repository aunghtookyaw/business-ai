"""Shared browser shell and navigation for the local BigShot Business OS."""

from __future__ import annotations

import logging
import subprocess
from datetime import datetime
from html import escape
from pathlib import Path

from flask import redirect, request, send_file


LOGGER = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOGO_PATH = PROJECT_ROOT / "dashboard-prototype" / "assets" / "bigshot-logo.jpg"

PLACEHOLDERS = {
    "customers": "Customers",
    "inventory": "Inventory",
    "financial": "Financial",
    "reports": "Reports",
    "settings": "System Information",
}


def _nav_item(path: str, label: str, active: str, key: str) -> str:
    current = " active" if active == key else ""
    marker = ' aria-current="page"' if current else ""
    return f'<a class="bos-nav-link{current}" href="{path}"{marker}>{escape(label)}</a>'


def render_shell(content: str, title: str, active: str = "dashboard") -> str:
    """Render one accessible, responsive shell around module content."""
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)} · BigShot Business OS</title>
<link rel="stylesheet" href="/static/business_os.css"></head>
<body class="bos-body"><a class="bos-skip" href="#main-content">Skip to content</a>
<div class="bos-layout">
  <aside class="bos-sidebar" id="businessOsSidebar" aria-label="Business OS navigation">
    <a class="bos-brand" href="/business-os"><img src="/business-os/assets/logo" alt="BigShot logo"><span>BigShot Business OS</span></a>
    <nav>
      {_nav_item('/business-os', 'Dashboard', active, 'dashboard')}
      <div class="bos-nav-group"><span>Sales</span>{_nav_item('/business-os/receive-payment', 'Receive Payment', active, 'receive-payment')}</div>
      <div class="bos-nav-group"><span>Production</span>{_nav_item('/business-os/veggies-production', 'Veggies Production', active, 'veggies-production')}{_nav_item('/business-os/veggies-production/crops', 'Veggies Crop Master', active, 'crop-master')}</div>
      {_nav_item('/business-os/customers', 'Customers', active, 'customers')}
      {_nav_item('/business-os/inventory', 'Inventory', active, 'inventory')}
      {_nav_item('/business-os/financial', 'Financial', active, 'financial')}
      {_nav_item('/business-os/reports', 'Reports', active, 'reports')}
      {_nav_item('/business-os/settings', 'Settings', active, 'settings')}
    </nav>
    <div class="bos-status">Local Business OS<br><span>127.0.0.1 only</span></div>
  </aside>
  <div class="bos-workspace">
    <header class="bos-header"><button class="bos-menu" type="button" aria-controls="businessOsSidebar" aria-expanded="false">Menu</button><div><span>Current module</span><h1>{escape(title)}</h1></div><a href="/business-os">Business OS Home</a></header>
    <main class="bos-main" id="main-content">{content}</main>
  </div>
</div><script src="/static/business_os.js"></script></body></html>'''


def _extract_body(html: str) -> str:
    lower = html.lower()
    start = lower.find("<body")
    if start < 0:
        return html
    start = html.find(">", start) + 1
    end = lower.rfind("</body>")
    body = html[start:end if end >= 0 else len(html)]
    # Legacy module headers duplicate the shared current-module header.
    stripped = body.lstrip()
    if stripped.lower().startswith("<header"):
        close = stripped.lower().find("</header>")
        if close >= 0:
            body = stripped[close + len("</header>"):]
    return body


def integrate_module_html(html: str, title: str, active: str) -> str:
    """Wrap legacy module markup without changing its business behavior."""
    replacements = (
        ('/veggies-production', '/business-os/veggies-production'),
        ('/receive-payment-basic', '/business-os/receive-payment'),
    )
    lower = html.lower()
    styles = []
    cursor = 0
    while True:
        start = lower.find("<style", cursor)
        if start < 0:
            break
        start_content = html.find(">", start) + 1
        end = lower.find("</style>", start_content)
        if end < 0:
            break
        styles.append(html[start_content:end])
        cursor = end + len("</style>")
    body = (f'<style>{"".join(styles)}</style>' if styles else "") + _extract_body(html)
    for old, new in replacements:
        body = body.replace(old, new)
    return render_shell(f'<div class="bos-module">{body}</div>', title, active)


def _git_version() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=PROJECT_ROOT,
            check=True, capture_output=True, text=True, timeout=2,
        ).stdout.strip()
    except Exception:
        return "Unavailable"


def _database_health(connect) -> tuple[str, str]:
    try:
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            connection.rollback()
        return "Connected", "good"
    except Exception:
        LOGGER.warning("Business OS database health check failed")
        return "Unavailable", "bad"


def register_business_os(app, connect) -> None:
    """Register the unified shell around already-registered module routes."""
    app.add_url_rule(
        "/business-os/receive-payment", "business_os_receive_payment",
        app.view_functions["receive_payment_basic_page"], methods=["GET", "POST"],
    )
    aliases = (
        ("/business-os/veggies-production", "business_os_veggies_production", "veggies_production_basic", ["GET", "POST"]),
        ("/business-os/veggies-production/crops", "business_os_crop_master", "veggies_crop_master_page", ["GET"]),
        ("/business-os/veggies-production/crops/<int:crop_id>", "business_os_crop_update", "veggies_crop_master_update", ["POST"]),
        ("/business-os/veggies-production/<int:batch_id>", "business_os_production_detail", "veggies_production_detail", ["GET"]),
        ("/business-os/veggies-production/<int:batch_id>/edit", "business_os_production_edit", "veggies_production_edit", ["GET", "POST"]),
    )
    for rule, endpoint, legacy_endpoint, methods in aliases:
        app.add_url_rule(rule, endpoint, app.view_functions[legacy_endpoint], methods=methods)

    @app.get("/business-os/assets/logo")
    def business_os_logo():
        return send_file(LOGO_PATH, mimetype="image/jpeg", conditional=True)

    @app.get("/business-os")
    def business_os_home():
        db_status, db_class = _database_health(connect)
        cards = (
            ("Receive Payment", "Record and review customer payments.", "/business-os/receive-payment", "Available"),
            ("Veggies Production", "Enter and review daily vegetable production.", "/business-os/veggies-production", "Available"),
            ("Veggies Crop Master", "Manage active crops and display settings.", "/business-os/veggies-production/crops", "Available"),
            ("Customers", "Customer operations module.", "/business-os/customers", "Coming Soon"),
            ("Inventory", "Inventory operations module.", "/business-os/inventory", "Coming Soon"),
            ("Financial", "Financial operations module.", "/business-os/financial", "Coming Soon"),
            ("Reports", "Business reports module.", "/business-os/reports", "Coming Soon"),
        )
        card_html = "".join(
            f'<a class="bos-module-card" href="{path}"><span>{escape(status)}</span><h2>{escape(name)}</h2><p>{escape(description)}</p></a>'
            for name, description, path, status in cards
        )
        now = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
        health = f'''<section class="bos-panel"><h2>System health</h2><div class="bos-health-grid">
          <div><span>PostgreSQL connection</span><strong class="{db_class}">{db_status}</strong></div>
          <div><span>Receive Payment module</span><strong class="good">Available</strong></div>
          <div><span>Veggies Production module</span><strong class="good">Available</strong></div>
          <div><span>Current local time</span><strong>{escape(now)}</strong></div>
          <div><span>Application version</span><strong>{escape(_git_version())}</strong></div>
        </div></section>'''
        return render_shell(f'<p class="bos-intro">One local workspace for daily BigShot operations.</p><div class="bos-module-grid">{card_html}</div>{health}', "Dashboard")

    for slug, title in PLACEHOLDERS.items():
        def placeholder(slug=slug, title=title):
            details = ""
            if slug == "settings":
                details = '<p>This installation is bound to the local interface. Unified authentication is planned for a future security sprint.</p>'
            return render_shell(f'<section class="bos-panel bos-placeholder"><h2>{escape(title)}</h2><p>Module planned for a future version.</p>{details}</section>', title, slug)
        app.add_url_rule(f"/business-os/{slug}", f"business_os_{slug}", placeholder, methods=["GET"])

    @app.after_request
    def business_os_shell(response):
        if not request.path.startswith("/business-os/") or request.path.startswith("/business-os/assets/"):
            return response
        location = response.headers.get("Location")
        if location:
            response.headers["Location"] = location.replace("/veggies-production", "/business-os/veggies-production").replace("/receive-payment-basic", "/business-os/receive-payment")
        if response.status_code < 300 and response.mimetype == "text/html":
            titles = {
                "business_os_receive_payment": ("Receive Payment", "receive-payment"),
                "business_os_veggies_production": ("Veggies Production", "veggies-production"),
                "business_os_crop_master": ("Veggies Crop Master", "crop-master"),
                "business_os_crop_update": ("Veggies Crop Master", "crop-master"),
                "business_os_production_detail": ("Veggies Production", "veggies-production"),
                "business_os_production_edit": ("Veggies Production", "veggies-production"),
            }
            info = titles.get(request.endpoint)
            if info:
                response.set_data(integrate_module_html(response.get_data(as_text=True), *info))
                response.headers["Content-Length"] = str(len(response.get_data()))
        return response

    @app.errorhandler(404)
    def not_found(_error):
        return render_shell('<section class="bos-panel bos-error"><h2>Page not found</h2><p>The requested Business OS page does not exist.</p><a class="bos-button" href="/business-os">Return to Business OS Home</a></section>', "404 Not Found", ""), 404

    @app.errorhandler(500)
    def internal_error(error):
        LOGGER.exception("Unhandled Business OS error", exc_info=error)
        return render_shell('<section class="bos-panel bos-error"><h2>Something went wrong</h2><p>The request could not be completed. Technical details were logged locally.</p><a class="bos-button" href="/business-os">Return to Business OS Home</a></section>', "Internal Server Error", ""), 500


def root_redirect():
    return redirect("/business-os", code=302)
