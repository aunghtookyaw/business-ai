import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

from pypdf import PdfReader

import business_os_app as receive_payment_server
from tools import sotephwar_voucher_pdf, sotephwar_voucher_repository, voucher_engine


class SotePhwarVoucherTest(unittest.TestCase):
    def draft(self, amount_received="0", lines=None):
        return {
            "id": 71, "sector": "sotephwar", "status": "previewed", "voucher_number": "SP-9001",
            "voucher_date": "2026-07-18", "customer_id": 7, "customer_name": "Dealer One",
            "customer_snapshot": {"id": 7, "customer_name": "Dealer One", "phone_number": "09123", "town": "Heho", "contact_address": "Main Road", "payment_terms_days": 30},
            "payment_method": "Cash", "amount_received": amount_received, "note": "Voucher note",
            "lines": lines or [
                {"product_code": "1l", "quantity": "2", "unit_price": "33000", "note": ""},
                {"product_code": "500ml", "quantity": "3", "unit_price": "17000", "note": "Line note"},
            ],
        }

    def test_fixed_four_products_and_selling_prices(self):
        self.assertEqual(
            [
                ("4l", "Sote Phwar 4L", "120000.00"),
                ("1l", "Sote Phwar 1L", "33000.00"),
                ("500ml", "Sote Phwar 500 mL", "17000.00"),
                ("100ml", "Sote Phwar 100 mL", "5000.00"),
            ],
            [(row["code"], row["item"], row["default_selling_price"]) for row in sotephwar_voucher_repository.products()],
        )

    def test_editable_price_and_decimal_safe_totals(self):
        preview = voucher_engine.preview_sotephwar(self.draft(lines=[
            {"product_code": "1l", "quantity": "3", "unit_price": "33000.00"},
            {"product_code": "100ml", "quantity": "7", "unit_price": "5001.00"},
        ]))
        self.assertEqual(Decimal("134007.00"), preview["total_amount"])
        self.assertEqual(Decimal("5001.00"), preview["lines"][1]["unit_price"])
        self.assertEqual("Sote Phwar 100 mL", preview["lines"][1]["item"])

    def test_negative_and_overpayment_are_rejected(self):
        with self.assertRaises(voucher_engine.VoucherValidationError):
            voucher_engine.preview_sotephwar(self.draft(lines=[{"product_code": "1l", "quantity": -1, "unit_price": 33000}]))
        with self.assertRaises(voucher_engine.VoucherValidationError) as raised:
            voucher_engine.preview_sotephwar(self.draft(amount_received="117001"))
        self.assertIn("amount_received cannot exceed net_amount", raised.exception.errors)

    def test_adjustments_free_items_and_exact_line_reconciliation(self):
        draft = self.draft(amount_received="50000")
        draft.update({
            "discount_amount": "10001", "cashback_amount": "2000", "adjustment_reason": "Dealer offer",
            "free_lines": [
                {"product_code": "4l", "quantity": 1, "description": "tampered", "unit": "case", "note": "Gift"},
                {"product_code": "100ml", "quantity": 2, "note": "Samples"},
            ],
        })
        voucher = voucher_engine.preview_sotephwar(draft)
        rows = voucher_engine.sotephwar_transaction_rows(draft)
        self.assertEqual(Decimal("117000.00"), voucher["gross_amount"])
        self.assertEqual(Decimal("104999.00"), voucher["net_amount"])
        self.assertEqual("Sote Phwar 4L", voucher["free_lines"][0]["description"])
        self.assertEqual("bottle", voucher["free_lines"][0]["unit"])
        self.assertEqual(Decimal("104999.00"), sum((row["Total_Amount"] for row in rows), Decimal("0")))
        self.assertEqual(Decimal("50000.00"), sum((row["Total_Received"] for row in rows), Decimal("0")))
        self.assertEqual(Decimal("54999.00"), sum((row["Outstanding_Balance"] for row in rows), Decimal("0")))
        self.assertEqual(2, len(rows))

    def test_free_item_validation_and_zero_financial_effect(self):
        base = self.draft()
        without = voucher_engine.preview_sotephwar(base)
        with_free = voucher_engine.preview_sotephwar({**base, "free_lines": [{"product_code": "1l", "quantity": 3}]})
        self.assertEqual(without["gross_amount"], with_free["gross_amount"])
        self.assertEqual(without["net_amount"], with_free["net_amount"])
        for free_lines in ([{"product_code": "1l", "quantity": 0}],
                           [{"product_code": "bad", "quantity": 1}],
                           [{"product_code": "1l", "quantity": 1}, {"product_code": "1l", "quantity": 2}]):
            with self.assertRaises(voucher_engine.VoucherValidationError):
                voucher_engine.preview_sotephwar({**base, "free_lines": free_lines})

    def test_zero_partial_and_full_allocations(self):
        expected = [
            ("0", [Decimal("0.00"), Decimal("0.00")], ["Outstanding", "Outstanding"]),
            ("58500", [Decimal("33000.00"), Decimal("25500.00")], ["Partial", "Partial"]),
            ("117000", [Decimal("66000.00"), Decimal("51000.00")], ["Paid", "Paid"]),
        ]
        for received, allocations, statuses in expected:
            rows = voucher_engine.sotephwar_transaction_rows(self.draft(amount_received=received))
            self.assertEqual(allocations, [row["Total_Received"] for row in rows])
            self.assertEqual(statuses, [row["Payment_Status"] for row in rows])
            self.assertEqual(Decimal(received), sum((row["Total_Received"] for row in rows), Decimal("0")))

    def test_rounding_remainder_is_reconciled_on_final_line(self):
        rows = voucher_engine.sotephwar_transaction_rows(self.draft(amount_received="100", lines=[
            {"product_code": "100ml", "quantity": 1, "unit_price": 5000},
            {"product_code": "100ml", "quantity": 1, "unit_price": 5000},
            {"product_code": "100ml", "quantity": 1, "unit_price": 5000},
        ]))
        self.assertEqual([Decimal("33.33"), Decimal("33.33"), Decimal("33.34")], [row["Total_Received"] for row in rows])
        self.assertEqual(Decimal("100.00"), sum((row["Total_Received"] for row in rows), Decimal("0")))

    def test_customer_filter_is_sotephwar_or_both_and_active(self):
        base = {"customer_name": "Dealer", "active": True}
        self.assertTrue(sotephwar_voucher_repository._customer_is_eligible({**base, "customer_group": "SotePhwar"}))
        self.assertTrue(sotephwar_voucher_repository._customer_is_eligible({**base, "customer_group": "Both"}))
        self.assertFalse(sotephwar_voucher_repository._customer_is_eligible({**base, "customer_group": "Farm"}))
        self.assertFalse(sotephwar_voucher_repository._customer_is_eligible({**base, "customer_group": "SotePhwar", "active": False}))

    def test_pdf_uses_sotephwar_heading_and_product_details(self):
        preview = voucher_engine.preview_sotephwar(self.draft(amount_received="58500"))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sotephwar.pdf"
            sotephwar_voucher_pdf.write_sotephwar_voucher_pdf(preview, path)
            text = "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
        self.assertIn("SOTEPHWAR", text)
        self.assertIn("SALES", text)
        self.assertIn("INVOICE", text)
        self.assertIn("Sote Phwar 1L", text)
        self.assertIn("Sote Phwar 500 mL", text)
        self.assertIn("117,000.00 MMK", text)
        for heading in ("BOTTLE SUMMARY", "Bottle Type", "Paid Qty", "Free Qty", "Total Qty"):
            self.assertIn(heading, text)
        for bottle_type in ("4L", "1L", "500 mL", "100 mL"):
            self.assertIn(bottle_type, text)
        self.assertIn("No promotional free items.", text)
        for signature in ("Customer", "Warehouse", "Delivery", "Sales Representative"):
            self.assertIn(signature, text)

    def test_pdf_separates_free_items_and_adjustment_summary(self):
        draft = self.draft(amount_received="50000")
        draft.update({"discount_amount": 1000, "cashback_amount": 500,
                      "adjustment_reason": "Dealer promotion",
                      "free_lines": [{"product_code": "100ml", "quantity": 2, "note": "Samples"}]})
        preview = voucher_engine.preview_sotephwar(draft)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "free-items.pdf"
            sotephwar_voucher_pdf.write_sotephwar_voucher_pdf(preview, path)
            text = "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
        for expected in ("FREE ITEMS", "Sote Phwar 100 mL", "Samples", "GROSS AMOUNT", "DISCOUNT", "CASHBACK", "NET AMOUNT", "Dealer promotion"):
            self.assertIn(expected, text)
        self.assertIn("BOTTLE SUMMARY", text)

    def test_pdf_bottle_summary_separates_every_canonical_bottle_type(self):
        preview = voucher_engine.preview_sotephwar({
            **self.draft(lines=[
                {"product_code": "1l", "quantity": 1000, "unit_price": 33000},
                {"product_code": "500ml", "quantity": 1000, "unit_price": 17000},
            ]),
            "free_lines": [
                {"product_code": "1l", "quantity": 10},
                {"product_code": "500ml", "quantity": 5},
            ],
        })
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "large-quantity.pdf"
            sotephwar_voucher_pdf.write_sotephwar_voucher_pdf(preview, path)
            reader = PdfReader(str(path))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        self.assertEqual(1, len(reader.pages))
        summary_lines = [line.strip() for line in text.splitlines()]
        expected_rows = {
            "4L": ("0", "0", "0"),
            "1L": ("1000", "10", "1010"),
            "500 mL": ("1000", "5", "1005"),
            "100 mL": ("0", "0", "0"),
        }
        for label, values in expected_rows.items():
            start = summary_lines.index(label, summary_lines.index("BOTTLE SUMMARY"))
            self.assertEqual(values, tuple(summary_lines[start + 1:start + 4]))
        self.assertNotIn("2015 Bottles", text)
        self.assertNotIn("1000.00", "\n".join(summary_lines[summary_lines.index("BOTTLE SUMMARY"):]))

    def test_pdf_summary_typography_stays_within_document_scale(self):
        source = Path(sotephwar_voucher_pdf.__file__).read_text()
        self.assertNotIn("sp-kpi-value", source)
        self.assertIn('fontSize=12', source)
        self.assertIn('fontSize=10', source)

    def test_historical_payload_defaults_adjustments_and_free_lines(self):
        row = {"id": 2, "lines": [], "amount_received": Decimal("10"), "total_amount": Decimal("20"),
               "voucher_metadata": None, "submitted_voucher": None, "submitted_transaction_ids": None}
        payload = sotephwar_voucher_repository._payload(row)
        self.assertEqual("0", payload["discount_amount"])
        self.assertEqual("0", payload["cashback_amount"])
        self.assertEqual([], payload["free_lines"])

    @patch("tools.sotephwar_voucher_repository.get_draft")
    @patch("tools.sotephwar_voucher_repository._prepare_final_pdf")
    def test_atomic_multi_line_submit_creates_links_and_never_inventory(self, prepare_pdf, get_draft):
        get_draft.return_value = self.draft(amount_received="58500")
        with tempfile.TemporaryDirectory() as directory:
            pdf = Path(directory) / "final.pdf"; pdf.write_bytes(b"%PDF-test")
            prepare_pdf.return_value = (pdf, "a" * 64)
            connection = MagicMock()
            cursor = connection.cursor.return_value.__enter__.return_value
            saved = {**get_draft.return_value, "status": "submitted", "submitted_transaction_ids": [801, 802]}
            cursor.fetchone.side_effect = [None, {"id": 7}, {"id": 801}, {"id": 802}, saved]
            result = sotephwar_voucher_repository.submit(71, "tester", connection=connection)
        self.assertEqual([801, 802], result["transaction_ids"])
        sql_calls = "\n".join(str(call.args[0]) for call in cursor.execute.call_args_list)
        self.assertEqual(2, sql_calls.count("_nc_m2m_Sotephwar_Trans_customer_master"))
        self.assertNotIn("Sotephwar_Inventory", sql_calls)
        connection.commit.assert_called_once()

    @patch("tools.sotephwar_voucher_repository.get_draft")
    @patch("tools.sotephwar_voucher_repository._prepare_final_pdf")
    def test_submit_requires_validation_and_does_not_generate_pdf(self, prepare_pdf, get_draft):
        get_draft.return_value = {**self.draft(), "status": "draft"}
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        with self.assertRaisesRegex(voucher_engine.VoucherValidationError, "validated before submit"):
            sotephwar_voucher_repository.submit(71, "tester", connection=connection)
        prepare_pdf.assert_not_called()
        connection.rollback.assert_called_once()
        cursor.execute.assert_not_called()

    @patch("tools.sotephwar_voucher_repository.get_draft")
    @patch("tools.sotephwar_voucher_repository._prepare_final_pdf")
    def test_database_failure_rolls_back_without_generating_pdf(self, prepare_pdf, get_draft):
        get_draft.return_value = self.draft()
        with tempfile.TemporaryDirectory() as directory:
            pdf = Path(directory) / "prepared.pdf"; pdf.write_bytes(b"%PDF-test")
            prepare_pdf.return_value = (pdf, "b" * 64)
            connection = MagicMock()
            cursor = connection.cursor.return_value.__enter__.return_value
            cursor.fetchone.side_effect = [None, {"id": 7}]
            def fail_on_transaction_insert(statement, params=None):
                if 'INSERT INTO' in str(statement) and 'Sotephwar_Transection' in str(statement):
                    raise RuntimeError("database insert failed")
            cursor.execute.side_effect = fail_on_transaction_insert
            with self.assertRaisesRegex(RuntimeError, "database insert failed"):
                sotephwar_voucher_repository.submit(71, "tester", connection=connection)
            self.assertFalse(pdf.exists())
            prepare_pdf.assert_called_once()
        connection.rollback.assert_called_once()

    @patch("tools.sotephwar_voucher_repository.get_draft")
    def test_duplicate_submitted_draft_is_idempotent(self, get_draft):
        get_draft.return_value = {"id": 71, "status": "submitted", "submitted_transaction_ids": [801, 802]}
        connection = MagicMock()
        result = sotephwar_voucher_repository.submit(71, "tester", connection=connection)
        self.assertTrue(result["idempotent"])
        self.assertEqual([801, 802], result["transaction_ids"])
        connection.commit.assert_not_called()

    def test_business_os_page_has_searchable_customer_and_editable_prices(self):
        client = receive_payment_server.app.test_client()
        html = client.get("/business-os/sotephwar-voucher").get_data(as_text=True)
        script = (Path(__file__).resolve().parents[1] / "static/sotephwar_voucher.js").read_text()
        self.assertIn('list="svCustomerOptions"', html)
        self.assertIn('data-f="unit_price"', script)
        self.assertIn("Submit to SotePhwar Transactions", html)
        self.assertIn("/pdf?inline=1", script)

    def test_submitted_voucher_delete_is_atomic_and_scoped(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.side_effect = [
            {"id": 55, "sector": "sotephwar", "status": "submitted", "is_deleted": False,
             "voucher_number": "SP-55", "voucher_date": "2026-07-22", "customer_name": "Test Dealer",
             "submitted_transaction_id": 700, "submitted_transaction_ids": [700, 701], "submitted_pdf_path": None},
            {"count": 0},
            {"id": 55},
        ]
        result = sotephwar_voucher_repository.delete_submitted_voucher(
            55, "SP-55", "Confirmed test voucher", "Business OS", connection=connection,
        )
        self.assertTrue(result["deleted"])
        self.assertEqual([700, 701], result["transaction_ids"])
        sql_calls = "\n".join(str(call.args[0]) for call in cursor.execute.call_args_list)
        self.assertIn("_nc_m2m_Sotephwar_Trans_customer_master", sql_calls)
        self.assertIn("Sotephwar_Transection", sql_calls)
        self.assertIn("business_os_voucher_draft", sql_calls)
        self.assertNotIn("Sotephwar_Inventory", sql_calls)
        self.assertNotIn("DELETE FROM Identifier('pipkgfu2wr9qxyy').Identifier('Payment_Receive')", sql_calls)
        connection.commit.assert_called_once()

    def test_submitted_voucher_delete_refuses_payment_history(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.side_effect = [
            {"id": 55, "sector": "sotephwar", "status": "submitted", "is_deleted": False,
             "voucher_number": "SP-55", "voucher_date": "2026-07-22", "customer_name": "Dealer",
             "submitted_transaction_ids": [700]},
            {"count": 1},
        ]
        with self.assertRaisesRegex(ValueError, "payment history"):
            sotephwar_voucher_repository.delete_submitted_voucher(
                55, "SP-55", "Test cleanup", "Business OS", connection=connection,
            )
        connection.rollback.assert_called_once()
        connection.commit.assert_not_called()

    def test_submitted_voucher_delete_requires_exact_number_and_reason(self):
        with self.assertRaisesRegex(ValueError, "Type the voucher number"):
            sotephwar_voucher_repository.delete_submitted_voucher(55, "", "reason", "Business OS", connection=MagicMock())
        with self.assertRaisesRegex(ValueError, "Deletion reason"):
            sotephwar_voucher_repository.delete_submitted_voucher(55, "SP-55", "", "Business OS", connection=MagicMock())

    def test_submitted_voucher_delete_endpoint_is_protected(self):
        client = receive_payment_server.app.test_client()
        url = "/business-os/api/sotephwar-voucher/history/55/delete"
        self.assertEqual(403, client.post(url, json={}).status_code)
        result = {"deleted": True, "draft_id": 55, "voucher_number": "SP-55", "customer_name": "Dealer",
                  "transaction_ids": [700], "pdf_path": None, "deleted_by": "Business OS", "reason": "Test"}
        with patch.object(sotephwar_voucher_repository, "delete_submitted_voucher", return_value=result) as delete:
            response = client.post(url, json={"voucher_number": "SP-55", "reason": "Test"},
                                   headers={"X-Business-OS-Request": "draft-management-v1"})
        self.assertEqual(200, response.status_code)
        self.assertTrue(response.get_json()["deleted"])
        delete.assert_called_once_with(55, "SP-55", "Test", "Business OS")

    def test_sotephwar_history_has_guarded_delete_controls(self):
        client = receive_payment_server.app.test_client()
        html = client.get("/business-os/sotephwar-voucher").get_data(as_text=True)
        history = (Path(__file__).resolve().parents[1] / "static/operational_history.js").read_text()
        self.assertIn("Delete Submitted Voucher", html)
        self.assertIn("opDeleteVoucherConfirm", html)
        self.assertIn("data-history-delete", history)
        self.assertIn("confirmation:$('opDeleteVoucherConfirm').value", history)
        self.assertIn("reason:$('opDeleteVoucherReason').value", history)

    def test_migration_is_additive_and_farm_sources_are_unchanged(self):
        root = Path(__file__).resolve().parents[1]
        migration = (root / "migrations/20260718_009_sotephwar_voucher_submission_ids_up.sql").read_text()
        self.assertIn("ADD COLUMN IF NOT EXISTS submitted_transaction_ids", migration)
        self.assertNotIn("Sotephwar_Inventory", migration)
        self.assertNotIn("DROP TABLE", migration.upper())
        self.assertEqual("", __import__("subprocess").run(
            ["git", "diff", "--", "static/farm_voucher.js"],
            cwd=root, capture_output=True, text=True, check=True,
        ).stdout)


if __name__ == "__main__":
    unittest.main()
