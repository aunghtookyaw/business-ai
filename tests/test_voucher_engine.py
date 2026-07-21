import unittest
from decimal import Decimal

from tools import voucher_engine


class VoucherEngineTest(unittest.TestCase):
    def test_payment_method_uses_supported_voucher_types(self):
        self.assertEqual(
            ("Cash", "KPay", "AYA Pay", "UAB Pay", "Other Online Pay"),
            voucher_engine.PAYMENT_METHODS,
        )
        draft = voucher_engine.new_draft("farm")
        draft.update({"voucher_number": "1", "customer_name": "Market", "payment_method": "Bank transfer"})
        with self.assertRaises(voucher_engine.VoucherValidationError) as raised:
            voucher_engine.validate(draft)
        self.assertIn("payment_method must be Cash, KPay, AYA Pay, UAB Pay, or Other Online Pay", raised.exception.errors)

    def test_farm_workflow_validates_previews_and_maps_rows(self):
        draft = voucher_engine.new_draft("farm")
        draft.update({
            "voucher_number": "101", "voucher_date": "2026-07-16",
            "customer_id": 12, "customer_name": "Home Market", "payment_method": "Cash",
            "lines": [{"description": "Beetroot", "quantity": "2.5", "unit": "kg", "unit_price": "1200"}],
        })
        validated = voucher_engine.validate(draft)
        self.assertEqual("validated", validated["status"])
        preview = voucher_engine.preview(draft)
        self.assertEqual(Decimal("3000.00"), preview["total_amount"])
        rows = voucher_engine.farm_transaction_rows(draft)
        self.assertEqual("101", rows[0]["Invoice_Number"])
        self.assertEqual(Decimal("3000.00"), rows[0]["Total_Amount"])
        self.assertEqual(Decimal("3000.00"), rows[0]["Outstanding_Balance"])
        self.assertEqual({
            "Date", "Customer", "Invoice_Number", "Total_Amount", "Total_Received",
            "Outstanding_Balance", "Payment_Status",
        }, set(rows[0]))
        self.assertNotIn("Beetroot", str(rows[0]))

    def test_validation_collects_errors_and_never_mutates_draft(self):
        draft = {"sector": "farm", "voucher_date": "bad", "lines": [{"quantity": 0, "unit_price": -1}]}
        with self.assertRaises(voucher_engine.VoucherValidationError) as raised:
            voucher_engine.validate(draft)
        self.assertIn("voucher_number is required", raised.exception.errors)
        self.assertNotIn("status", draft)

    def test_shared_engine_accepts_sotephwar_but_farm_mapper_rejects_it(self):
        draft = {
            "sector": "sotephwar", "voucher_number": "S-1", "voucher_date": "2026-07-16",
            "customer_name": "Dealer", "payment_method": "Cash", "lines": [{"description": "1 L", "quantity": 2, "unit": "bottle", "unit_price": 100}],
        }
        self.assertEqual("previewed", voucher_engine.preview(draft)["status"])
        with self.assertRaisesRegex(ValueError, "Farm"):
            voucher_engine.farm_transaction_rows(draft)

    def test_multiple_delivery_dates_prices_subtotals_and_one_aggregate(self):
        draft = {
            "sector": "farm", "voucher_number": "701", "voucher_date": "2026-07-16",
            "customer_name": "Market", "payment_method": "Cash", "amount_received": "500",
            "delivery_sections": [
                {"delivery_date": "2026-07-12", "items": [
                    {"crop_id": 4, "crop_name": "Beetroot", "custom_description": "", "quantity": 2, "unit": "kg", "unit_price": 1000, "note": "first price"},
                ]},
                {"delivery_date": "2026-07-10", "items": [
                    {"crop_id": 4, "crop_name": "Beetroot", "custom_description": "", "quantity": 3, "unit": "kg", "unit_price": 1200},
                    {"crop_id": None, "crop_name": "", "custom_description": "Gift basket", "quantity": 1, "unit": "set", "unit_price": 400},
                ]},
            ],
        }
        preview = voucher_engine.preview(draft)
        self.assertEqual(["2026-07-10", "2026-07-12"], [row["delivery_date"] for row in preview["delivery_sections"]])
        self.assertEqual([Decimal("4000.00"), Decimal("2000.00")], [row["subtotal"] for row in preview["delivery_sections"]])
        self.assertEqual(Decimal("6000.00"), preview["total_amount"])
        self.assertEqual(Decimal("5500.00"), preview["outstanding_balance"])
        rows = voucher_engine.farm_transaction_rows(draft)
        self.assertEqual(1, len(rows))
        self.assertEqual(Decimal("6000.00"), rows[0]["Total_Amount"])
        self.assertEqual("2026-07-16", rows[0]["Date"])
        self.assertNotIn("2026-07-10", str(rows[0]))
        self.assertNotIn("Gift basket", str(rows[0]))

    def test_payment_status_summary_mapping(self):
        base = {
            "sector": "farm", "voucher_number": "706", "voucher_date": "2026-07-16",
            "customer_id": 1, "customer_name": "Market", "payment_method": "Cash",
            "delivery_sections": [{"delivery_date": "2026-07-10", "items": [
                {"custom_description": "A", "quantity": 1, "unit": "kg", "unit_price": 100},
            ]}],
        }
        expected = [(0, "Outstanding", Decimal("100.00")), (25, "Partial", Decimal("75.00")), (100, "Paid", Decimal("0.00"))]
        for received, status, outstanding in expected:
            row = voucher_engine.farm_transaction_rows({**base, "amount_received": received})[0]
            self.assertEqual(status, row["Payment_Status"])
            self.assertEqual(Decimal(str(received)).quantize(Decimal("0.01")), row["Total_Received"])
            self.assertEqual(outstanding, row["Outstanding_Balance"])

    def test_duplicate_date_sections_merge_safely(self):
        base = {"sector": "farm", "voucher_number": "702", "voucher_date": "2026-07-16", "customer_name": "Market", "payment_method": "Cash"}
        base["delivery_sections"] = [
            {"delivery_date": "2026-07-10", "items": [{"custom_description": "A", "quantity": 1, "unit": "kg", "unit_price": 2}]},
            {"delivery_date": "2026-07-10", "items": [{"custom_description": "B", "quantity": 1, "unit": "kg", "unit_price": 3}]},
        ]
        preview = voucher_engine.preview(base)
        self.assertEqual(1, len(preview["delivery_sections"]))
        self.assertEqual(2, len(preview["delivery_sections"][0]["items"]))
        self.assertEqual(Decimal("5.00"), preview["total_amount"])

    def test_existing_flat_draft_becomes_custom_item_on_invoice_date(self):
        old = {
            "sector": "farm", "voucher_number": "703", "voucher_date": "2026-07-09",
            "customer_name": "Market", "payment_method": "Cash", "lines": [{"description": "Legacy free text", "quantity": 2, "unit": "kg", "unit_price": 5}],
        }
        preview = voucher_engine.preview(old)
        item = preview["delivery_sections"][0]["items"][0]
        self.assertEqual("2026-07-09", preview["delivery_sections"][0]["delivery_date"])
        self.assertIsNone(item["crop_id"])
        self.assertEqual("Legacy free text", item["custom_description"])

    def test_crop_or_custom_is_exclusive_and_amount_received_cannot_exceed_total(self):
        invalid = {
            "sector": "farm", "voucher_number": "704", "voucher_date": "2026-07-09", "customer_name": "Market", "payment_method": "Cash",
            "amount_received": 10, "delivery_sections": [{"delivery_date": "2026-07-09", "items": [
                {"crop_id": 1, "crop_name": "Crop", "custom_description": "Also custom", "quantity": 1, "unit": "kg", "unit_price": 5},
            ]}],
        }
        with self.assertRaises(voucher_engine.VoucherValidationError) as raised:
            voucher_engine.preview(invalid)
        self.assertTrue(any("exactly one" in error for error in raised.exception.errors))

        overpaid = {
            "sector": "farm", "voucher_number": "705", "voucher_date": "2026-07-09", "customer_name": "Market", "payment_method": "Cash",
            "amount_received": 6, "delivery_sections": [{"delivery_date": "2026-07-09", "items": [
                {"custom_description": "A", "quantity": 1, "unit": "kg", "unit_price": 5},
            ]}],
        }
        with self.assertRaises(voucher_engine.VoucherValidationError) as overpaid_error:
            voucher_engine.preview(overpaid)
        self.assertIn("amount_received cannot exceed net_amount", overpaid_error.exception.errors)

    def test_farm_adjustments_are_authoritative_whole_mmk_and_map_net(self):
        base = {
            "sector": "farm", "voucher_number": "800", "voucher_date": "2026-07-21",
            "customer_name": "Market", "payment_method": "Cash", "amount_received": 600,
            "discount_amount": 250, "cashback_amount": 150, "adjustment_reason": "Promotion",
            "delivery_sections": [{"delivery_date": "2026-07-21", "items": [
                {"custom_description": "Produce", "quantity": 2, "unit": "kg", "unit_price": 500},
            ]}],
        }
        voucher = voucher_engine.preview(base)
        self.assertEqual(Decimal("1000.00"), voucher["gross_amount"])
        self.assertEqual(Decimal("600.00"), voucher["net_amount"])
        self.assertEqual(Decimal("0.00"), voucher["outstanding_balance"])
        self.assertEqual("Paid", voucher["payment_status"])
        self.assertEqual(Decimal("600.00"), voucher_engine.farm_transaction_rows(base)[0]["Total_Amount"])
        for changes, message in (({"discount_amount": -1}, "cannot be negative"),
                                 ({"cashback_amount": "1.5"}, "whole MMK"),
                                 ({"discount_amount": 1001, "cashback_amount": 0}, "cannot exceed gross_amount"),
                                 ({"discount_amount": 500, "amount_received": 501}, "cannot exceed net_amount")):
            with self.assertRaises(voucher_engine.VoucherValidationError) as raised:
                voucher_engine.preview({**base, **changes})
            self.assertTrue(any(message in error for error in raised.exception.errors))

    def test_browser_supplied_totals_are_ignored(self):
        draft = {
            "sector": "farm", "voucher_number": "801", "voucher_date": "2026-07-21",
            "customer_name": "Market", "payment_method": "Cash", "total_amount": 999999,
            "gross_amount": 999999, "net_amount": 1, "outstanding_balance": -10,
            "delivery_sections": [{"delivery_date": "2026-07-21", "items": [
                {"custom_description": "Produce", "quantity": 2, "unit": "kg", "unit_price": 500},
            ]}],
        }
        voucher = voucher_engine.preview(draft)
        self.assertEqual(Decimal("1000.00"), voucher["gross_amount"])
        self.assertEqual(Decimal("1000.00"), voucher["net_amount"])
        self.assertEqual(Decimal("1000.00"), voucher["outstanding_balance"])
