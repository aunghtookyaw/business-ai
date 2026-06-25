from pathlib import Path
import re
import unittest
from unittest.mock import patch

from scripts import dashboard_server


class DashboardServerTest(unittest.TestCase):
    def setUp(self):
        self.client = dashboard_server.app.test_client()

    def test_health_declares_read_only(self):
        response = self.client.get("/health")
        self.assertEqual(200, response.status_code)
        self.assertTrue(response.get_json()["read_only"])
        self.assertEqual("DENY", response.headers["X-Frame-Options"])

    @patch("scripts.dashboard_server.dashboard_service.executive_dashboard")
    def test_executive_api_returns_bi_service_payload(self, executive_dashboard):
        executive_dashboard.return_value = ({"metrics": {"revenue": 123}}, False)
        response = self.client.post(
            "/api/dashboard/executive",
            json={"filters": {"period": {"type": "year", "year": 2026}}},
        )

        self.assertEqual(200, response.status_code)
        self.assertEqual(123, response.get_json()["data"]["metrics"]["revenue"])
        executive_dashboard.assert_called_once()

    def test_invalid_filter_returns_400(self):
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
