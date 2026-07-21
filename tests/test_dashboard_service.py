import unittest
from unittest.mock import patch

from tools import dashboard_service, formula_engine


class DashboardServiceTest(unittest.TestCase):
    def setUp(self):
        dashboard_service.clear_dashboard_cache()

    def test_parse_dashboard_filters_validates_period_and_status(self):
        filters = dashboard_service.parse_dashboard_filters({
            "filters": {
                "period": {"type": "month", "year": 2026, "month": 6},
                "sector": "Sote Phwar",
                "business_unit": "sote_phwar",
                "payment_status": "Partial",
            }
        })

        self.assertEqual("month:2026-06", dashboard_service.legacy_period(filters.period))
        self.assertEqual("Sote Phwar", filters.sector)
        self.assertEqual("Partial", filters.payment_status)

        with self.assertRaisesRegex(ValueError, "payment_status"):
            dashboard_service.parse_dashboard_filters({
                "filters": {
                    "period": {"type": "year", "year": 2026},
                    "payment_status": "Deleted",
                }
            })

    @patch("tools.dashboard_service._trend_periods", return_value=[("Jun", "month:2026-06")])
    @patch("tools.dashboard_service.formula_engine.list_transactions")
    @patch("tools.dashboard_service.formula_engine.recent_payment_receipts")
    @patch("tools.dashboard_service.formula_engine.top_expense_categories")
    @patch("tools.dashboard_service.formula_engine.sotephwar_product_ranking")
    @patch("tools.dashboard_service.formula_engine.top_income")
    @patch("tools.dashboard_service.formula_engine.calculate_inventory_value")
    @patch("tools.dashboard_service.formula_engine.payment_receive_summary")
    @patch("tools.dashboard_service.formula_engine.sales_total")
    @patch("tools.dashboard_service.formula_engine.cash_flow")
    @patch("tools.dashboard_service.formula_engine.kpi_overview")
    def test_executive_dashboard_passes_through_canonical_values(
        self,
        kpi,
        cash,
        sales,
        receivables,
        inventory,
        top_customers,
        top_products,
        expense_categories,
        payments,
        transactions,
        _trend_periods,
    ):
        kpi.return_value = {
            "total_income": 1000,
            "total_expense": 400,
            "net_profit": 600,
            "profit_margin_percent": 60,
        }
        cash.return_value = {"total_inflow": 700, "total_outflow": 400, "net_cash_flow": 300}
        sales.return_value = {"amount_received": 700, "outstanding_amount": 300}
        receivables.return_value = {
            "outstanding_receivables": 300,
            "collection_rate_percent": 70,
            "total_received": 700,
        }
        inventory.return_value = {
            "total_inventory_value": 160000,
            "stock": [
                {
                    "store": "A",
                    "product": "Sote Phwar 1L",
                    "stock_qty": 5,
                    "unit_cost": 32000,
                    "inventory_value": 160000,
                }
            ],
            "locations": [{"store": "A", "qty": 5, "inventory_value": 160000}],
        }
        top_customers.return_value = {"income": [{"customer_name": "C", "total_amount": 1000}]}
        top_products.return_value = {"products": [{"product": "P", "quantity": 5}]}
        expense_categories.return_value = {"categories": [{"category": "E", "amount": 400}]}
        payments.return_value = {"payments": [{"id": 1, "receive_amount": 100}]}
        transactions.return_value = {"transactions": [{"id": 2, "amount": 50}]}
        filters = dashboard_service.parse_dashboard_filters({
            "filters": {"period": {"type": "year", "year": 2026}}
        })

        result, cached = dashboard_service.executive_dashboard(filters)

        self.assertFalse(cached)
        self.assertEqual(1000, result["metrics"]["revenue"])
        self.assertEqual(400, result["metrics"]["expenses"])
        self.assertEqual(600, result["metrics"]["net_profit"])
        self.assertEqual(700, result["metrics"]["cash_received"])
        self.assertEqual(300, result["metrics"]["outstanding_receivables"])
        self.assertEqual(160000, result["metrics"]["inventory_value"])
        self.assertEqual(160000, result["inventory"]["locations"][0]["inventory_value"])
        self.assertEqual(1000, result["trend"][0]["revenue"])
        self.assertEqual(300, result["trend"][0]["cash_flow"])

    def test_cached_dashboard_does_not_reexecute_loader(self):
        filters = dashboard_service.parse_dashboard_filters({
            "filters": {"period": {"type": "year", "year": 2026}}
        })
        calls = []

        def loader():
            calls.append(True)
            return {"ok": True}

        first, first_cached = dashboard_service._cached("test", filters, 30, loader)
        second, second_cached = dashboard_service._cached("test", filters, 30, loader)

        self.assertEqual(first, second)
        self.assertFalse(first_cached)
        self.assertTrue(second_cached)
        self.assertEqual(1, len(calls))

    @patch("tools.dashboard_service.formula_engine.recent_payment_receipts")
    @patch("tools.dashboard_service.formula_engine.payment_receive_summary")
    def test_payments_dashboard_uses_canonical_reports_and_labels_invoice_age(self, summary, receipts):
        summary.return_value = {
            "total_invoice_amount": 1000, "total_received": 400,
            "outstanding_receivables": 600, "collection_rate_percent": 40,
            "aging": {"0-30": 600}, "customer_balances": [{"customer": "C", "outstanding_balance": 600}],
            "sector_totals": [], "invoices": [{"received_amount": 400, "outstanding_balance": 600}],
        }
        receipts.return_value = {"payments": [{"id": 1, "receive_amount": 400}]}
        filters = dashboard_service.parse_dashboard_filters({"filters": {"period": {"type": "year", "year": 2026}}})
        result = dashboard_service.payments_dashboard(filters)
        self.assertEqual(600, result["metrics"]["outstanding"])
        self.assertEqual("Partial", result["invoices"][0]["payment_status"])
        self.assertIn("invoice age", result["data_quality"][0]["message"])
        summary.assert_called_once_with("year:2026", sector=None, customer=None, payment_status=None, limit=100)

    def test_payments_query_contract_is_frozen(self):
        self.assertEqual(
            {
                "version": "payments-v1-2026-07-16",
                "read_only": True,
                "voucher_identity": ["sector", "voucher_number", "invoice_date", "customer"],
                "period_basis": {"receivables": "invoice_date", "receipts": "receive_date"},
                "sources": ["payment_receive_summary", "recent_payment_receipts"],
                "row_limit": 100,
                "voucher_order": ["outstanding_balance DESC", "invoice_date ASC NULLS LAST"],
                "receipt_order": ["receive_date DESC NULLS LAST", "id DESC"],
                "aging_semantics": "invoice_age_not_due_date",
            },
            dashboard_service.PAYMENTS_QUERY_CONTRACT,
        )

    @patch("tools.formula_engine._fetch_all")
    @patch("tools.formula_engine.ensure_payment_receive_table")
    def test_live_payment_formula_sql_contract_keeps_identity_filters_and_ordering(self, _ensure, fetch_all):
        fetch_all.return_value = []
        formula_engine.payment_receive_summary(
            "year:2026", sector="Farm", customer="C", payment_status="Partial", limit=100,
        )
        summary_sql = fetch_all.call_args.args[0]
        self.assertIn("f.\"Invoice_Number\"::text", summary_sql)
        self.assertIn("f.\"Date\"", summary_sql)
        self.assertIn("invoices.customer", summary_sql)
        self.assertIn("p.\"Sector\" = invoices.sector", summary_sql)
        self.assertIn("p.\"Voucher_Number\" = invoices.voucher_number", summary_sql)
        self.assertIn("p.\"Invoice_Date\" = invoices.invoice_date", summary_sql)
        self.assertIn("ORDER BY outstanding_balance DESC", summary_sql)

        formula_engine.recent_payment_receipts(
            "year:2026", sector="Farm", customer="C", payment_status="Partial", limit=100,
        )
        receipt_sql = fetch_all.call_args.args[0]
        self.assertIn('"Receive_Date" AS receive_date', receipt_sql)
        self.assertIn('AND "Sector" = %(sector)s', receipt_sql)
        self.assertIn('COALESCE("Customer", \'\') = %(customer)s', receipt_sql)
        self.assertIn('ORDER BY "Receive_Date" DESC NULLS LAST, id DESC', receipt_sql)

    @patch("tools.dashboard_service.ask_ai", return_value="Executive Summary\n- Revenue is $10.")
    @patch("tools.dashboard_service.executive_dashboard")
    def test_qwen_narrative_rejects_numeric_or_currency_content(self, executive_dashboard, _ask_ai):
        executive_dashboard.return_value = ({
            "filter_label": "2026",
            "metrics": {},
            "cash_flow": {
                "total_inflow": 0,
                "total_outflow": 0,
                "net_cash_flow": 0,
            },
            "top_customers": [],
            "top_expense_categories": [],
            "data_quality": [],
        }, False)
        filters = dashboard_service.parse_dashboard_filters({
            "filters": {"period": {"type": "year", "year": 2026}}
        })

        with self.assertRaisesRegex(RuntimeError, "prohibited"):
            dashboard_service._build_executive_insight(filters)


if __name__ == "__main__":
    unittest.main()
