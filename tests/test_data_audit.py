import io
import os
import unittest
from unittest.mock import patch

from openpyxl import Workbook
from werkzeug.datastructures import FileStorage

from scripts import dashboard_server
from tools import data_audit


class DataAuditUnitTest(unittest.TestCase):
    def test_metadata_registry_is_limited_to_version_one_tables(self):
        self.assertEqual(
            {"sotephwar_transection", "farm_transection", "transection"},
            set(data_audit.TARGETS),
        )
        self.assertEqual(
            {"Sotephwar_Transection", "farm_transection", "Transection"},
            {target["table"] for target in data_audit.TARGETS.values()},
        )

    def test_mapping_uses_headers_not_position_for_all_targets(self):
        mapping, confidence, missing, conflicts = data_audit.detect_mapping(
            ["Total Amount", "Customer", "Date", "Voucher Number"], "farm_transection"
        )
        self.assertEqual(
            {"total_amount": 0, "customer_name": 1, "invoice_date": 2, "invoice_number": 3},
            mapping,
        )
        self.assertFalse(missing)
        self.assertFalse(conflicts)
        self.assertTrue(all(value == 1 for value in confidence.values()))

        mapping, _, missing, _ = data_audit.detect_mapping(
            ["Description", "Amount", "Category", "Income Expense", "Date"], "transection"
        )
        self.assertEqual(0, mapping["product"])
        self.assertEqual(4, mapping["invoice_date"])
        self.assertFalse(missing)

    def test_missing_required_mapping_is_reported(self):
        mapping, _, missing, _ = data_audit.detect_mapping(["Date", "Amount"], "sotephwar_transection")
        self.assertEqual({"invoice_date": 0, "total_amount": 1}, mapping)
        self.assertIn("invoice_number", missing)
        self.assertIn("quantity", missing)

    def test_alias_normalization_is_deterministic_and_persistent_alias_wins(self):
        aliases = {
            ("customer", data_audit.normalize_lookup("Khin Mar Cho,Daw")): "Daw Khin Mar Cho",
            ("product", data_audit.normalize_lookup("Special Bottle")): "Canonical Bottle",
        }
        self.assertEqual(
            "daw khin mar cho",
            data_audit._normalize_field("customer_name", "Khin Mar Cho,Daw", aliases),
        )
        self.assertEqual(
            "canonical bottle",
            data_audit._normalize_field("product", "Special Bottle", aliases),
        )
        self.assertEqual(
            "sote phwar 500 ml",
            data_audit._normalize_field("product", "Sote Phwar 500 ml", {}),
        )

    def test_xlsx_and_csv_profiles_are_read_without_modifying_sources(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Sales"
        sheet.append(["Date", "Amount"])
        sheet.append(["2026-01-01", 100])
        stream = io.BytesIO()
        workbook.save(stream)
        stream.seek(0)
        sheet_name, rows = data_audit._read_upload(FileStorage(stream=stream, filename="audit.xlsx"))
        self.assertEqual("Sales", sheet_name)
        self.assertEqual(["Date", "Amount"], rows[0])

        sheet_name, rows = data_audit._read_upload(
            FileStorage(stream=io.BytesIO(b"Date,Amount\n2026-01-01,100\n"), filename="audit.csv")
        )
        self.assertEqual("CSV", sheet_name)
        self.assertEqual(["2026-01-01", "100"], rows[1])


class DataAuditPortalTest(unittest.TestCase):
    def setUp(self):
        dashboard_server.app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)
        self.client = dashboard_server.app.test_client()

    def login(self, role="Admin"):
        with self.client.session_transaction() as session:
            session["username"] = "auditor"
            session["role"] = role

    def test_page_and_apis_require_existing_dashboard_authentication(self):
        self.assertEqual(302, self.client.get("/data-audit").status_code)
        self.assertEqual(302, self.client.get("/excel-import").status_code)
        self.assertEqual(401, self.client.get("/api/data-audit/history").status_code)

    def test_authenticated_page_contains_workflow_and_assets(self):
        self.login()
        response = self.client.get("/data-audit")
        html = response.get_data(as_text=True)
        self.assertEqual(200, response.status_code)
        for label in (
            "Upload Excel", "Run Audit", "Review Differences", "Apply Changes",
            "Audit History", "Customer Aliases", "Product Aliases",
        ):
            self.assertIn(label, html)
        self.assertEqual(200, self.client.get("/data-audit.css").status_code)
        self.assertEqual(200, self.client.get("/data-audit.js").status_code)
        self.assertEqual(200, self.client.get("/excel-import").status_code)

    @patch("tools.data_audit_portal.data_audit.get_audit", return_value={"created_by": "another-user"})
    def test_normal_user_cannot_access_another_users_audit_session(self, get_audit):
        self.login("Viewer")
        response = self.client.get("/api/data-audit/41")
        self.assertEqual(403, response.status_code)

    @patch("tools.data_audit_portal.data_audit.list_history", return_value={"audits": [], "page": 1, "page_size": 20, "total": 0, "pages": 1})
    def test_normal_user_can_run_review_and_download_history(self, history):
        self.login("Viewer")
        response = self.client.get("/api/data-audit/history")
        self.assertEqual(200, response.status_code)
        history.assert_called_once()

    @patch("tools.data_audit_portal.data_audit.apply_audit")
    def test_normal_user_cannot_apply_changes(self, apply_audit):
        self.login("Viewer")
        response = self.client.post("/api/data-audit/7/apply")
        self.assertEqual(403, response.status_code)
        self.assertEqual("administrator_required", response.get_json()["code"])
        apply_audit.assert_not_called()

    @patch("tools.data_audit_portal.data_audit.apply_audit", return_value={"audit_id": 7, "changes_applied": 2, "status": "applied"})
    def test_admin_can_apply_changes(self, apply_audit):
        self.login("Admin")
        response = self.client.post("/api/data-audit/7/apply")
        self.assertEqual(200, response.status_code)
        self.assertEqual(2, response.get_json()["changes_applied"])
        apply_audit.assert_called_once_with(7, "auditor")

    def test_dashboard_navigation_exposes_data_audit_admin_menu(self):
        html = (dashboard_server.STATIC_ROOT / "index.html").read_text()
        self.assertIn("Admin", html)
        self.assertIn('href="/data-audit"', html)


if __name__ == "__main__":
    unittest.main()
