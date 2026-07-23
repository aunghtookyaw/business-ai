import tempfile
import unittest
from io import BytesIO
import hashlib
from pathlib import Path
from unittest.mock import MagicMock, patch

from pypdf import PdfReader

from scripts import dashboard_server
import business_os_app
from tools import farm_voucher_pdf, farm_voucher_repository, voucher_engine


class FarmVoucherTest(unittest.TestCase):
    def setUp(self):
        self.draft = {
            "sector": "farm", "voucher_number": "900001", "voucher_date": "2026-07-16",
            "customer_id": 90, "customer_name": "Ma Nge", "payment_method": "Cash",
            "amount_received": "1000", "note": "Local verification",
            "lines": [{"description": "Beetroot", "quantity": "2", "unit": "kg", "unit_price": "1500"}],
        }

    def test_preview_calculates_payment_status_and_farm_aggregate(self):
        preview = voucher_engine.preview(self.draft)
        self.assertEqual("Partial", preview["payment_status"])
        self.assertEqual("2000.00", str(preview["outstanding_balance"]))
        row = voucher_engine.farm_transaction_rows(self.draft)[0]
        self.assertEqual("Partial", row["Payment_Status"])
        self.assertEqual("3000.00", str(row["Total_Amount"]))

    def test_submitted_delete_is_scoped_and_blocks_payments(self):
        connection=MagicMock();cursor=connection.cursor.return_value.__enter__.return_value
        submitted={**self.draft,"id":8,"status":"submitted","is_deleted":False,"submitted_transaction_id":91,"submitted_pdf_path":None}
        cursor.fetchone.side_effect=[submitted,{"count":0},{"id":8}]
        result=farm_voucher_repository.delete_submitted_voucher(8,"900001","test cleanup","Business OS",connection=connection)
        self.assertTrue(result["deleted"]);connection.commit.assert_called_once()
        statements="\n".join(str(call.args[0]) for call in cursor.execute.call_args_list)
        self.assertIn("farm_transection",statements);self.assertNotIn("Sotephwar_Inventory",statements)
        blocked=MagicMock();blocked_cursor=blocked.cursor.return_value.__enter__.return_value
        blocked_cursor.fetchone.side_effect=[submitted,{"count":1}]
        with self.assertRaisesRegex(ValueError,"payment history"):
            farm_voucher_repository.delete_submitted_voucher(8,"900001","test cleanup","Business OS",connection=blocked)
        blocked.rollback.assert_called_once()

    def test_a4_pdf_renders_voucher(self):
        multi = {**self.draft, "lines": [], "delivery_sections": [
            {"delivery_date": "2026-07-10", "items": [{"custom_description": "Custom A", "quantity": 1, "unit": "kg", "unit_price": 1000}]},
            {"delivery_date": "2026-07-12", "items": [{"crop_id": 1, "crop_name": "Beetroot", "quantity": 2, "unit": "kg", "unit_price": 1000}]},
        ]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "farm.pdf"
            preview = voucher_engine.preview(multi)
            farm_voucher_pdf.write_farm_voucher_pdf(preview, path)
            content = path.read_bytes()
            self.assertTrue(content.startswith(b"%PDF-"))
            self.assertGreater(len(content), 1000)
            self.assertEqual(["2026-07-10", "2026-07-12"], [section["delivery_date"] for section in preview["delivery_sections"]])

    def test_customer_filter_accepts_only_active_farm_and_both(self):
        base = {"customer_name": "Customer", "active": True}
        self.assertTrue(farm_voucher_repository._customer_is_eligible({**base, "customer_group": "Farm"}))
        self.assertTrue(farm_voucher_repository._customer_is_eligible({**base, "customer_group": "Both"}))
        self.assertFalse(farm_voucher_repository._customer_is_eligible({**base, "customer_group": "SotePhwar"}))
        self.assertFalse(farm_voucher_repository._customer_is_eligible({**base, "customer_group": "Farm", "active": False}))

    def test_customer_snapshot_autofill_preserves_phone_text_and_blank_address(self):
        snapshot = farm_voucher_repository._snapshot_from_customer({
            "id": 7, "customer_name": "Farm Shop", "phone_number": "091234567",
            "town": "Yangon", "contact_address": None, "payment_terms_days": 30,
            "customer_group": "Farm", "active": True,
        })
        self.assertEqual("091234567", snapshot["phone_number"])
        self.assertEqual("Yangon", snapshot["town"])
        self.assertEqual("", snapshot["contact_address"])
        self.assertEqual(30, snapshot["payment_terms_days"])

    @patch("tools.farm_voucher_repository._load_customer_snapshot")
    def test_existing_draft_snapshot_is_stable_when_master_changes(self, load):
        saved = {"id": 7, "customer_name": "Original", "phone_number": "091", "town": "Old Town"}
        current = {"customer_id": 7, "customer_snapshot": saved}
        result = farm_voucher_repository._draft_customer_snapshot({"customer_id": 7}, current, object())
        self.assertIs(saved, result)
        load.assert_not_called()

    def test_preview_and_print_use_same_customer_snapshot(self):
        snapshot = {"customer_name": "Ma Nge", "phone_number": "09111", "town": "Hmawbi", "contact_address": "Farm Road"}
        preview = voucher_engine.preview({**self.draft, "customer_snapshot": snapshot})
        self.assertEqual(snapshot, preview["customer_snapshot"])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "customer.pdf"
            farm_voucher_pdf.write_farm_voucher_pdf(preview, path)
            self.assertGreater(path.stat().st_size, 1000)

    def test_preview_document_and_extracted_pdf_contain_identical_business_data(self):
        snapshot = {
            "customer_name": "Farm Buyer", "phone_number": "091234567",
            "town": "Heho", "contact_address": "No. 10 Farm Road",
            "customer_group": "Farm", "payment_terms_days": 30,
        }
        draft = {
            **self.draft, "voucher_number": "900777", "customer_name": "Farm Buyer",
            "customer_snapshot": snapshot, "lines": [],
            "delivery_sections": [
                {"delivery_date": "2026-07-10", "items": [
                    {"crop_id": 1, "crop_name": "Beetroot", "quantity": 2, "unit": "kg", "unit_price": 1500},
                ]},
                {"delivery_date": "2026-07-12", "items": [
                    {"custom_description": "Gift Basket", "quantity": 3, "unit": "set", "unit_price": 2000},
                ]},
            ],
        }
        preview = voucher_engine.preview(draft)
        document = farm_voucher_pdf.voucher_document(preview)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "shared-preview-print.pdf"
            farm_voucher_pdf.write_farm_voucher_pdf(preview, path)
            extracted = "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
        expected = [
            document["customer_name"], document["phone_number"], document["contact_address"],
            document["invoice_number"], document["invoice_date"], "2026-07-10", "2026-07-12",
            "Beetroot", "Gift Basket", "2.00", "3.00", "1,500.00 MMK", "2,000.00 MMK",
            "3,000.00 MMK", "6,000.00 MMK", document["grand_total"],
            document["amount_received"], document["outstanding"],
        ]
        for value in expected:
            self.assertIn(value, extracted, f"missing extracted PDF data: {value}")
        self.assertNotIn("Customer Group", extracted)
        self.assertNotIn("Payment Status", extracted)

    def test_brand_address_payment_files_and_customer_grid_are_exact(self):
        root = Path(__file__).resolve().parents[1]
        preview = voucher_engine.preview({
            **self.draft,
            "customer_snapshot": {
                "phone_number": "091234567", "contact_address": "Farm Road",
                "payment_terms_days": 30,
            },
        })
        document = farm_voucher_pdf.voucher_document(preview)
        address_lines = (root / "static/brand-assets/address.txt").read_text().splitlines()
        payment_lines = (root / "static/brand-assets/payment.txt").read_text().splitlines()
        self.assertEqual(address_lines, document["brand_address_lines"])
        self.assertEqual(payment_lines, document["payment_information_lines"])
        self.assertEqual(2, len(farm_voucher_pdf.CUSTOMER_GRID_FIELDS))
        self.assertEqual([3, 3], [len(row) for row in farm_voucher_pdf.CUSTOMER_GRID_FIELDS])
        self.assertAlmostEqual(1, sum(farm_voucher_pdf.HEADER_COLUMN_PROPORTIONS))
        self.assertEqual(28, farm_voucher_pdf.HEADER_HEIGHT_MM)
        self.assertTrue(farm_voucher_pdf.TRANSPARENT_LOGO_PATH.exists())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "brand-payment.pdf"
            farm_voucher_pdf.write_farm_voucher_pdf(preview, path)
            extracted = "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
        normalized = " ".join(extracted.split())
        self.assertIn(" ".join(address_lines[0].split()), normalized)
        for segment in address_lines[1].split(","):
            self.assertIn(" ".join(segment.split()), normalized)
        for label, value in farm_voucher_pdf._payment_rows(payment_lines):
            self.assertIn(label, extracted)
            self.assertIn(value, extracted)
        self.assertNotIn("BigShot Farm", extracted)
        self.assertNotIn("Prepared by", extracted)
        self.assertNotIn("Authorized signature", extracted)
        self.assertNotIn("Customer signature", extracted)
        self.assertIn("Signature", extracted)
        self.assertIn("GROSS AMOUNT", extracted)
        self.assertIn("NET AMOUNT", extracted)
        self.assertIn("PAID", extracted)
        self.assertIn("TOTAL DUE", extracted)
        self.assertIn("PLEASE MAKE PAYMENT TO:", extracted)

    def test_long_voucher_anchors_payment_once_on_last_page(self):
        items = [
            {"custom_description": f"Harvest item {index:02d}", "quantity": index, "unit": "kg", "unit_price": 1000 + index}
            for index in range(1, 43)
        ]
        preview = voucher_engine.preview({
            **self.draft,
            "customer_snapshot": {"phone_number": "091234567", "contact_address": "Farm Road", "payment_terms_days": 30},
            "lines": [],
            "delivery_sections": [{"delivery_date": "2026-07-16", "items": items}],
        })
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "long-voucher.pdf"
            farm_voucher_pdf.write_farm_voucher_pdf(preview, path)
            page_texts = [page.extract_text() or "" for page in PdfReader(str(path)).pages]
        self.assertGreater(len(page_texts), 1)
        self.assertTrue(all("PLEASE MAKE PAYMENT TO:" not in text for text in page_texts[:-1]))
        self.assertIn("PLEASE MAKE PAYMENT TO:", page_texts[-1])
        self.assertIn("Signature", page_texts[-1])
        self.assertEqual(1, sum(text.count("NET AMOUNT") for text in page_texts))

    def test_preview_uses_the_same_pdf_endpoint_as_print(self):
        root = Path(__file__).resolve().parents[1]
        script = (root / "static/farm_voucher.js").read_text()
        self.assertIn("/pdf?inline=1", script)
        self.assertIn("location.href=`${api}/drafts/${draft.id}/pdf`", script)
        self.assertNotIn("fv-preview-section", script)

    def test_customer_ui_is_searchable_and_shows_blank_address_fallback(self):
        root = Path(__file__).resolve().parents[1]
        page = (root / "tools/farm_voucher_portal.py").read_text()
        script = (root / "static/farm_voucher.js").read_text()
        self.assertIn('list="fvCustomerOptions"', page)
        self.assertIn("customer_name||''} — ${row.town||''} — ${row.phone_number||''", script)
        self.assertIn("Address not added", script)

    def test_snapshot_migration_is_additive_and_draft_only(self):
        root = Path(__file__).resolve().parents[1]
        migration = (root / "migrations/20260716_007_farm_voucher_customer_snapshot_up.sql").read_text()
        self.assertIn("ADD COLUMN IF NOT EXISTS customer_snapshot", migration)
        self.assertIn("business_os_voucher_draft", migration)
        self.assertNotIn("farm_transection", migration)
        self.assertNotIn("DROP TABLE", migration.upper())

    def test_submission_artifact_migration_is_additive_and_draft_only(self):
        root = Path(__file__).resolve().parents[1]
        migration = (root / "migrations/20260716_008_farm_voucher_submission_artifacts_up.sql").read_text()
        self.assertIn("submitted_voucher", migration)
        self.assertIn("submitted_pdf_path", migration)
        self.assertIn("submitted_pdf_checksum", migration)
        self.assertIn("business_os_voucher_draft", migration)
        self.assertNotIn("farm_transection", migration)
        self.assertNotIn("DROP TABLE", migration.upper())

    def test_submit_ui_requires_validation_not_pdf_and_locks_submitted_editor(self):
        root = Path(__file__).resolve().parents[1]
        script = (root / "static/farm_voucher.js").read_text()
        self.assertIn("pdfReady=false", script)
        self.assertIn("!['validated','previewed'].includes(draft.status)", script)
        self.assertIn("Preview/PDF generation failed", script)
        self.assertIn("const submitted=draft?.status==='submitted'", script)
        for label in ("Invoice number:", "Customer:", "Invoice date:", "Net amount:", "Received:", "Outstanding:"):
            self.assertIn(label, script)

    def test_final_pdf_helper_preserves_json_details_and_checksum(self):
        preview = voucher_engine.preview({
            **self.draft,
            "customer_snapshot": {"phone_number": "091234567", "contact_address": "Farm Road", "town": "Heho"},
        })
        with tempfile.TemporaryDirectory() as directory:
            path, checksum = farm_voucher_repository._prepare_final_pdf(77, preview, directory)
            self.assertTrue(path.is_file())
            self.assertEqual(64, len(checksum))
            stored = {"submitted_pdf_path": str(path), "submitted_pdf_checksum": checksum}
            self.assertEqual(path, farm_voucher_repository.submitted_pdf_path(stored))
            extracted = "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
        self.assertIn("091234567", extracted)
        self.assertIn("Farm Road", extracted)
        self.assertIn("Beetroot", extracted)

    def test_submitted_pdf_defaults_to_current_payment_statement_and_preserves_original(self):
        submitted = voucher_engine.preview({
            **self.draft,
            "amount_received": "880000",
            "lines": [{"description": "Beetroot", "quantity": "1", "unit": "kg", "unit_price": "1880000"}],
            "customer_snapshot": {"phone_number": "091234567", "contact_address": "Farm Road"},
        })
        with tempfile.TemporaryDirectory() as directory:
            original = Path(directory) / "original.pdf"
            farm_voucher_pdf.write_farm_voucher_pdf(submitted, original)
            original_checksum = hashlib.sha256(original.read_bytes()).hexdigest()
            draft = {"id": 77, "status": "submitted", "submitted_voucher": submitted}
            current = {"invoice_amount": 1880000, "current_received": 1880000, "current_outstanding": 0,
                       "current_payment_status": "Paid", "latest_payment_date": "2026-07-20"}
            client = business_os_app.app.test_client()
            with patch("tools.farm_voucher_portal.farm_voucher_repository.get_draft", return_value=draft), \
                 patch("tools.farm_voucher_portal.farm_voucher_repository.submitted_pdf_path", return_value=original), \
                 patch("tools.farm_voucher_portal.current_voucher_payment_state", return_value=current):
                current_response = client.get("/business-os/api/farm-voucher/drafts/77/pdf")
                original_response = client.get("/business-os/api/farm-voucher/drafts/77/pdf?original=1")

            current_text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(current_response.data)).pages)
            original_text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(original_response.data)).pages)
            self.assertEqual(200, current_response.status_code)
            self.assertIn("Beetroot", current_text)
            self.assertIn("PAYMENT", current_text)
            self.assertIn("STATUS", current_text)
            self.assertIn("PAID", current_text)
            self.assertIn("0.00 MMK", current_text)
            self.assertIn("880,000.00 MMK", original_text)
            self.assertEqual(original_checksum, hashlib.sha256(original.read_bytes()).hexdigest())

    @patch("tools.farm_voucher_repository.get_draft")
    @patch("tools.farm_voucher_repository._connect")
    def test_duplicate_submit_is_idempotent(self, connect, get_draft):
        connection = connect.return_value
        get_draft.return_value = {"id": 7, "status": "submitted", "submitted_transaction_id": 44}
        result = farm_voucher_repository.submit(7, "tester")
        self.assertTrue(result["idempotent"])
        self.assertEqual(44, result["transaction_id"])
        connection.commit.assert_not_called()

    @patch("tools.farm_voucher_repository.get_draft")
    def test_submit_requires_validation_and_does_not_generate_pdf(self, get_draft):
        get_draft.return_value = {**self.draft, "id": 7, "status": "draft"}
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        with patch("tools.farm_voucher_repository._prepare_final_pdf") as prepare_pdf:
            with self.assertRaisesRegex(voucher_engine.VoucherValidationError, "validated before submit"):
                farm_voucher_repository.submit(7, "tester", connection=connection)
        prepare_pdf.assert_not_called()
        connection.rollback.assert_called_once()
        cursor.execute.assert_not_called()

    @patch("tools.farm_voucher_repository.get_draft")
    def test_submitted_voucher_cannot_be_edited(self, get_draft):
        get_draft.return_value = {"id": 7, "status": "submitted", "version": 3}
        with self.assertRaisesRegex(ValueError, "cannot be edited"):
            farm_voucher_repository.update_draft(7, {}, 3)

    def test_farm_voucher_apis_require_authentication(self):
        client = dashboard_server.app.test_client()
        self.assertEqual(401, client.get("/api/vouchers/farm/drafts").status_code)
        self.assertEqual(401, client.post("/api/vouchers/farm/drafts", json={}).status_code)
        self.assertEqual(401, client.post("/api/vouchers/farm/drafts/1/submit").status_code)

    @patch.dict("os.environ", {"MASTER_USERNAME": "master", "MASTER_PASSWORD": "secret", "DASHBOARD_COOKIE_SECURE": "0"})
    @patch("scripts.dashboard_server.farm_voucher_repository.create_draft")
    def test_authenticated_draft_api(self, create):
        create.return_value = {"id": 1, "status": "draft"}
        client = dashboard_server.app.test_client()
        self.assertEqual(200, client.post("/api/auth/login", json={"username": "master", "password": "secret"}).status_code)
        response = client.post("/api/vouchers/farm/drafts", json=self.draft)
        self.assertEqual(201, response.status_code)
        self.assertEqual("draft", response.get_json()["draft"]["status"])
        create.assert_called_once()

    def test_additive_migration_backfills_flat_lines_as_custom_items(self):
        root = Path(__file__).resolve().parents[1]
        migration = (root / "migrations/20260716_006_farm_voucher_delivery_sections_up.sql").read_text()
        self.assertIn("ADD COLUMN IF NOT EXISTS delivery_sections", migration)
        self.assertIn("draft.voucher_date", migration)
        self.assertIn("'custom_description'", migration)
        self.assertNotIn("DROP TABLE", migration.upper())


if __name__ == "__main__":
    unittest.main()
