from pathlib import Path
import os
import re
import unittest
from unittest.mock import Mock, patch

from scripts import dashboard_server


class DashboardServerTest(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            "MASTER_USERNAME": "master",
            "MASTER_PASSWORD": "secret-password",
            "DASHBOARD_COOKIE_SECURE": "0",
            "DASHBOARD_SECRET_KEY": "test-session-secret",
            "DASHBOARD_INTERNAL_API_TOKEN": "test-internal-token",
        })
        self.env.start()
        dashboard_server._FAILED_LOGIN_ATTEMPTS.clear()
        self.client = dashboard_server.app.test_client()

    def tearDown(self):
        self.env.stop()

    def login(self):
        response = self.client.post(
            "/api/auth/login",
            json={"username": "master", "password": "secret-password"},
        )
        self.assertEqual(200, response.status_code)

    def test_health_reports_public_status(self):
        response = self.client.get("/health")
        self.assertEqual(200, response.status_code)
        self.assertEqual({
            "status": "healthy",
            "version": "1.0",
            "authenticated": False,
        }, response.get_json())
        self.assertEqual("DENY", response.headers["X-Frame-Options"])

    def test_ready_reports_required_runtime_checks(self):
        response = self.client.get("/ready")

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertEqual("ready", payload["status"])
        self.assertTrue(payload["checks"]["server"])
        self.assertTrue(payload["checks"]["environment"])
        self.assertTrue(payload["checks"]["session"])

    def test_ready_reports_missing_environment(self):
        with patch.dict(os.environ, {"MASTER_PASSWORD": ""}):
            response = self.client.get("/ready")

        self.assertEqual(503, response.status_code)
        self.assertEqual("not_ready", response.get_json()["status"])
        self.assertFalse(response.get_json()["checks"]["environment"])

    def test_session_cookie_security_settings_are_active(self):
        self.assertTrue(dashboard_server.app.config["SESSION_COOKIE_HTTPONLY"])
        self.assertEqual("Strict", dashboard_server.app.config["SESSION_COOKIE_SAMESITE"])
        self.assertEqual(10 * 60 * 60, dashboard_server.app.config["PERMANENT_SESSION_LIFETIME"].total_seconds())

    def test_dashboard_api_requires_login(self):
        response = self.client.post(
            "/api/dashboard/executive",
            json={"filters": {"period": {"type": "year", "year": 2026}}},
        )

        self.assertEqual(401, response.status_code)
        self.assertFalse(response.get_json()["ok"])

    def test_internal_api_rejects_missing_bearer_token(self):
        with self.assertLogs("bigshot.dashboard", level="WARNING") as logs:
            response = self.client.post(
                "/internal/v1/dashboard/executive",
                json={"filters": {"period": {"type": "year", "year": 2026}}},
            )

        self.assertEqual(401, response.status_code)
        self.assertFalse(response.get_json()["ok"])
        self.assertIn('"event": "internal_api_auth_failed"', logs.output[0])
        self.assertNotIn("test-internal-token", logs.output[0])

    def test_internal_api_rejects_wrong_bearer_token(self):
        with self.assertLogs("bigshot.dashboard", level="WARNING") as logs:
            response = self.client.get(
                "/internal/v1/dashboard/dimensions",
                headers={"Authorization": "Bearer wrong-token"},
            )

        self.assertEqual(401, response.status_code)
        self.assertFalse(response.get_json()["ok"])
        self.assertIn('"event": "internal_api_auth_failed"', logs.output[0])
        self.assertNotIn("wrong-token", logs.output[0])
        self.assertNotIn("test-internal-token", logs.output[0])

    @patch("scripts.dashboard_server.dashboard_service.dashboard_dimensions")
    def test_internal_dimensions_accepts_valid_bearer_token(self, dashboard_dimensions):
        dashboard_dimensions.return_value = {"years": [2026]}

        response = self.client.get(
            "/internal/v1/dashboard/dimensions",
            headers={"Authorization": "Bearer test-internal-token"},
        )

        self.assertEqual(200, response.status_code)
        self.assertEqual({"years": [2026]}, response.get_json()["data"])
        dashboard_dimensions.assert_called_once()

    def test_internal_health_accepts_valid_bearer_token(self):
        response = self.client.get(
            "/internal/v1/dashboard/health",
            headers={"Authorization": "Bearer test-internal-token"},
        )

        self.assertEqual(200, response.status_code)
        self.assertEqual("healthy", response.get_json()["status"])

    @patch("scripts.dashboard_server.dashboard_service.executive_dashboard")
    def test_internal_executive_api_accepts_valid_bearer_token_without_browser_login(self, executive_dashboard):
        executive_dashboard.return_value = ({"metrics": {"revenue": 456}}, False)

        response = self.client.post(
            "/internal/v1/dashboard/executive",
            json={"filters": {"period": {"type": "year", "year": 2026}}},
            headers={"Authorization": "Bearer test-internal-token"},
        )

        self.assertEqual(200, response.status_code)
        self.assertEqual(456, response.get_json()["data"]["metrics"]["revenue"])
        executive_dashboard.assert_called_once()

    def test_dashboard_page_redirects_to_login_when_logged_out(self):
        response = self.client.get("/payments")

        self.assertEqual(302, response.status_code)
        self.assertIn("login=required", response.headers["Location"])

    def test_dashboard_page_loads_after_login(self):
        self.login()

        response = self.client.get("/payments")

        self.assertEqual(200, response.status_code)
        self.assertIn(b"<title>BigShot Dashboard</title>", response.data)

    def test_pwa_manifest_and_icons_are_public(self):
        expected_assets = {
            "/static/manifest.webmanifest": "application/manifest+json",
            "/static/icons/favicon.ico": "image/x-icon",
            "/static/icons/bigshot-32.png": "image/png",
            "/static/icons/apple-touch-icon.png": "image/png",
            "/static/icons/bigshot-192.png": "image/png",
            "/static/icons/bigshot-512.png": "image/png",
        }

        for path, content_type in expected_assets.items():
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(200, response.status_code)
                self.assertTrue(response.content_type.startswith(content_type))

    def test_dashboard_html_contains_title_pwa_and_favicon_links(self):
        response = self.client.get("/")

        self.assertEqual(200, response.status_code)
        self.assertIn(b"<title>BigShot Dashboard</title>", response.data)
        self.assertIn(b'rel="manifest" href="/static/manifest.webmanifest"', response.data)
        self.assertIn(
            b'rel="apple-touch-icon" sizes="180x180" href="/static/icons/apple-touch-icon.png"',
            response.data,
        )
        self.assertIn(b'rel="icon" type="image/x-icon" href="/static/icons/favicon.ico"', response.data)
        self.assertIn(
            b'rel="icon" type="image/png" sizes="32x32" href="/static/icons/bigshot-32.png"',
            response.data,
        )

    def test_dashboard_html_contains_accessible_startup_screen(self):
        response = self.client.get("/")
        app_script = (dashboard_server.STATIC_ROOT / "app.js").read_text()

        self.assertEqual(200, response.status_code)
        self.assertIn(b'id="startupScreen"', response.data)
        self.assertIn(b'alt="Official BigShot logo"', response.data)
        self.assertIn(b"Business Intelligence Platform", response.data)
        self.assertIn("Loading…".encode("utf-8"), response.data)
        self.assertIn("finally {\n    startupScreen.hidden = true;", app_script)

    def test_login_rejects_wrong_password(self):
        with self.assertLogs("bigshot.dashboard", level="WARNING") as logs:
            response = self.client.post(
                "/api/auth/login",
                json={"username": "master", "password": "wrong"},
            )

        self.assertEqual(401, response.status_code)
        self.assertFalse(response.get_json()["ok"])
        self.assertEqual("Invalid username or password.", response.get_json()["error"])
        self.assertIn('"event": "login_failed"', logs.output[0])
        self.assertIn('"username": "master"', logs.output[0])
        self.assertNotIn("wrong", logs.output[0])
        self.assertNotIn("secret-password", logs.output[0])

    def test_login_rate_limits_after_five_failures_per_ip(self):
        for _ in range(5):
            response = self.client.post(
                "/api/auth/login",
                json={"username": "master", "password": "wrong"},
                headers={"X-Forwarded-For": "203.0.113.10"},
            )
            self.assertEqual(401, response.status_code)

        with self.assertLogs("bigshot.dashboard", level="WARNING") as logs:
            response = self.client.post(
                "/api/auth/login",
                json={"username": "master", "password": "secret-password"},
                headers={"X-Forwarded-For": "203.0.113.10"},
            )

        self.assertEqual(429, response.status_code)
        self.assertIn("Too many failed login attempts", response.get_json()["error"])
        self.assertIn('"event": "login_rate_limited"', logs.output[0])
        self.assertNotIn("secret-password", logs.output[0])

    def test_login_uses_master_environment_credentials(self):
        with self.assertLogs("bigshot.dashboard", level="INFO") as logs:
            response = self.client.post(
                "/api/auth/login",
                json={"username": "master", "password": "secret-password"},
            )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual("master", payload["user"]["username"])
        self.assertEqual("Admin", payload["user"]["role"])
        self.assertIn('"event": "login_success"', logs.output[0])
        self.assertIn('"role": "Admin"', logs.output[0])
        self.assertNotIn("secret-password", logs.output[0])

    def test_logout_clears_session(self):
        self.login()

        with self.assertLogs("bigshot.dashboard", level="INFO") as logs:
            response = self.client.post("/api/auth/logout")
        session_response = self.client.get("/api/auth/session")

        self.assertEqual(200, response.status_code)
        self.assertFalse(session_response.get_json()["authenticated"])
        self.assertIn('"event": "logout"', logs.output[0])
        self.assertNotIn("secret-password", logs.output[0])

    @patch("scripts.dashboard_server.dashboard_service.executive_dashboard")
    def test_executive_api_returns_bi_service_payload(self, executive_dashboard):
        self.login()
        executive_dashboard.return_value = ({"metrics": {"revenue": 123}}, False)
        response = self.client.post(
            "/api/dashboard/executive",
            json={"filters": {"period": {"type": "year", "year": 2026}}},
        )

        self.assertEqual(200, response.status_code)
        self.assertEqual(123, response.get_json()["data"]["metrics"]["revenue"])
        executive_dashboard.assert_called_once()

    @patch("scripts.dashboard_server.dashboard_service.executive_dashboard")
    @patch("scripts.dashboard_server.requests.request")
    def test_executive_api_proxies_to_internal_service_server_side(self, upstream_request, executive_dashboard):
        upstream_request.return_value = Mock(
            status_code=200,
            content=b'{"ok":true,"cached":false,"data":{"metrics":{"revenue":789}}}',
            headers={"Content-Type": "application/json"},
        )
        self.login()

        with patch.dict(os.environ, {
            "DASHBOARD_INTERNAL_API_BASE_URL": "http://127.0.0.1:6062/internal/v1/dashboard/",
        }):
            response = self.client.post(
                "/api/dashboard/executive",
                json={"filters": {"period": {"type": "year", "year": 2026}}},
                headers={"Authorization": "Bearer browser-supplied-token"},
            )

        self.assertEqual(200, response.status_code)
        self.assertEqual(789, response.get_json()["data"]["metrics"]["revenue"])
        upstream_request.assert_called_once()
        call = upstream_request.call_args
        self.assertEqual("POST", call.kwargs["method"])
        self.assertEqual(
            "http://127.0.0.1:6062/internal/v1/dashboard/executive",
            call.kwargs["url"],
        )
        self.assertEqual("Bearer test-internal-token", call.kwargs["headers"]["Authorization"])
        self.assertNotIn("browser-supplied-token", str(call.kwargs))
        executive_dashboard.assert_not_called()

    @patch("scripts.dashboard_server.dashboard_service.dashboard_dimensions")
    @patch("scripts.dashboard_server.requests.request")
    def test_dimensions_api_proxies_get_without_local_database_call(self, upstream_request, dashboard_dimensions):
        upstream_request.return_value = Mock(
            status_code=200,
            content=b'{"ok":true,"data":{"years":[2026]}}',
            headers={"Content-Type": "application/json"},
        )
        self.login()

        with patch.dict(os.environ, {
            "DASHBOARD_INTERNAL_API_BASE_URL": "http://127.0.0.1:6062/internal/v1/dashboard",
        }):
            response = self.client.get("/api/dashboard/dimensions")

        self.assertEqual(200, response.status_code)
        self.assertEqual([2026], response.get_json()["data"]["years"])
        self.assertEqual("GET", upstream_request.call_args.kwargs["method"])
        self.assertEqual(
            "http://127.0.0.1:6062/internal/v1/dashboard/dimensions",
            upstream_request.call_args.kwargs["url"],
        )
        dashboard_dimensions.assert_not_called()

    @patch("scripts.dashboard_server.dashboard_service.executive_dashboard")
    @patch("scripts.dashboard_server.requests.request")
    def test_proxy_does_not_fallback_to_local_logic_when_upstream_fails(self, upstream_request, executive_dashboard):
        upstream_request.side_effect = dashboard_server.requests.ConnectionError("tunnel unavailable")
        self.login()

        with patch.dict(os.environ, {
            "DASHBOARD_INTERNAL_API_BASE_URL": "http://127.0.0.1:6062/internal/v1/dashboard",
        }):
            response = self.client.post(
                "/api/dashboard/executive",
                json={"filters": {"period": {"type": "year", "year": 2026}}},
            )

        self.assertEqual(502, response.status_code)
        self.assertEqual("Dashboard data service is unavailable.", response.get_json()["error"])
        executive_dashboard.assert_not_called()

    @patch("scripts.dashboard_server.requests.request")
    def test_proxy_requires_server_side_token(self, upstream_request):
        self.login()

        with patch.dict(os.environ, {
            "DASHBOARD_INTERNAL_API_BASE_URL": "http://127.0.0.1:6062/internal/v1/dashboard",
            "DASHBOARD_INTERNAL_API_TOKEN": "",
        }):
            response = self.client.post(
                "/api/dashboard/executive",
                json={"filters": {"period": {"type": "year", "year": 2026}}},
            )

        self.assertEqual(503, response.status_code)
        self.assertEqual("Dashboard data service is not configured.", response.get_json()["error"])
        upstream_request.assert_not_called()

    @patch("scripts.dashboard_server.write_dashboard_pdf")
    @patch("scripts.dashboard_server.requests.request")
    def test_pdf_export_proxies_binary_response_and_headers(self, upstream_request, write_dashboard_pdf):
        upstream_request.return_value = Mock(
            status_code=200,
            content=b"%PDF-1.4\n% upstream dashboard\n",
            headers={
                "Content-Type": "application/pdf",
                "Content-Disposition": 'attachment; filename="BigShot_Executive_Dashboard.pdf"',
            },
        )
        self.login()

        with patch.dict(os.environ, {
            "DASHBOARD_INTERNAL_API_BASE_URL": "http://127.0.0.1:6062/internal/v1/dashboard",
        }):
            response = self.client.post(
                "/api/dashboard/export/pdf",
                json={"filters": {"period": {"type": "year", "year": 2026}}},
            )

        self.assertEqual(200, response.status_code)
        self.assertEqual("application/pdf", response.mimetype)
        self.assertIn("BigShot_Executive_Dashboard.pdf", response.headers["Content-Disposition"])
        self.assertEqual(
            "http://127.0.0.1:6062/internal/v1/dashboard/export/pdf",
            upstream_request.call_args.kwargs["url"],
        )
        write_dashboard_pdf.assert_not_called()

    @patch("scripts.dashboard_server.write_dashboard_pdf")
    @patch("scripts.dashboard_server.dashboard_service.executive_dashboard")
    def test_pdf_export_uses_full_dashboard_payload(self, executive_dashboard, write_dashboard_pdf):
        self.login()
        executive_dashboard.return_value = ({
            "filter_label": "2026",
            "metrics": {"revenue": 123, "inventory_value": 45},
            "trend": [{"label": "Jan", "revenue": 123}],
            "inventory": {"locations": [{"store": "Factory", "inventory_value": 45}]},
            "top_customers": [],
            "top_expense_categories": [],
            "top_products": [],
            "recent_payments": [],
            "recent_transactions": [],
        }, False)
        write_dashboard_pdf.side_effect = lambda data, path: Path(path).write_bytes(b"%PDF-1.4\n% dashboard\n")

        response = self.client.post(
            "/api/dashboard/export/pdf",
            json={"filters": {"period": {"type": "year", "year": 2026}}},
        )

        self.assertEqual(200, response.status_code)
        payload = write_dashboard_pdf.call_args.args[0]
        self.assertEqual(123, payload["metrics"]["revenue"])
        self.assertEqual(45, payload["inventory"]["locations"][0]["inventory_value"])
        self.assertEqual("application/pdf", response.mimetype)

    def test_invalid_filter_returns_400(self):
        self.login()
        response = self.client.post(
            "/api/dashboard/executive",
            json={
                "filters": {
                    "period": {"type": "year", "year": 2026},
                    "payment_status": "Deleted",
                }
            },
        )

        self.assertEqual(400, response.status_code)
        self.assertFalse(response.get_json()["ok"])

    def test_dashboard_browser_has_no_sql_or_database_driver(self):
        root = Path(__file__).resolve().parents[1] / "dashboard-prototype"
        browser_source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (root / "index.html", root / "app.js")
        ).lower()
        for forbidden in ("psycopg", "postgresql", "information_schema", "pg_catalog"):
            self.assertNotIn(forbidden, browser_source)
        self.assertIsNone(re.search(r"\bselect\b.+\bfrom\b", browser_source))
        self.assertIsNone(re.search(r"\binsert\s+into\b", browser_source))
        self.assertIsNone(re.search(r"\bupdate\b.+\bset\b", browser_source))
        self.assertIsNone(re.search(r"\bdelete\s+from\b", browser_source))


if __name__ == "__main__":
    unittest.main()
