import unittest
from unittest.mock import patch

from tools import bi_executor
from tools import dashboard_service
from tools import formula_engine
from tools.bi_intents import BIIntent


class SharedBusinessIntelligenceEngineTest(unittest.TestCase):
    def setUp(self):
        dashboard_service.clear_dashboard_cache()

    @patch("tools.dashboard_service._trend_periods", return_value=[])
    @patch("tools.formula_engine.list_transactions")
    @patch("tools.formula_engine.recent_payment_receipts")
    @patch("tools.formula_engine.top_expense_categories")
    @patch("tools.formula_engine.sotephwar_product_ranking")
    @patch("tools.formula_engine.top_income")
    @patch("tools.formula_engine.calculate_inventory_value")
    @patch("tools.formula_engine.payment_receive_summary")
    @patch("tools.formula_engine.sales_total")
    @patch("tools.formula_engine.cash_flow")
    @patch("tools.formula_engine.kpi_overview")
    def test_dashboard_and_telegram_wizard_use_same_kpi_values(
        self,
        kpi_overview,
        cash_flow,
        sales_total,
        payment_receive_summary,
        calculate_inventory_value,
        top_income,
        sotephwar_product_ranking,
        top_expense_categories,
        recent_payment_receipts,
        list_transactions,
        _trend_periods,
    ):
        kpi_overview.return_value = {
            "formula": "kpi_overview",
            "period": "year:2026",
            "total_income": 1000,
            "total_expense": 300,
            "net_profit": 700,
            "profit_margin_percent": 70,
            "amount_received": 800,
            "outstanding_amount": 200,
            "collection_rate_percent": 80,
            "sources": {"farm_transection_total_amount": 900, "transection_income": 100},
        }
        cash_flow.return_value = {
            "formula": "cash_flow",
            "period": "year:2026",
            "total_inflow": 800,
            "total_outflow": 300,
            "net_cash_flow": 500,
            "by_payment_method": [],
        }
        sales_total.return_value = {
            "formula": "sales_total",
            "period": "year:2026",
            "total_sales": 1000,
            "amount_received": 800,
            "outstanding_amount": 200,
        }
        payment_receive_summary.return_value = {
            "formula": "payment_receive_summary",
            "period": "year:2026",
            "outstanding_receivables": 200,
            "collection_rate_percent": 80,
            "total_received": 800,
            "invoices": [],
        }
        calculate_inventory_value.return_value = {
            "formula": "sotephwar_inventory_value",
            "total_inventory_value": 0,
            "stock": [],
            "products": [],
            "locations": [],
        }
        top_income.return_value = {"formula": "top_income", "income": []}
        sotephwar_product_ranking.return_value = {"formula": "sotephwar_product_ranking", "products": []}
        top_expense_categories.return_value = {"formula": "top_expense_categories", "categories": []}
        recent_payment_receipts.return_value = {"formula": "recent_payment_receipts", "payments": []}
        list_transactions.return_value = {"formula": "list_transactions", "transactions": []}

        direct = formula_engine.business_kpi_overview(
            "year:2026",
            business="farm",
            filters={"sector": "Farm"},
        )
        wizard = bi_executor.execute_intent(BIIntent(
            business="farm",
            module="kpi",
            report="kpi",
            period={"type": "month", "year": 2026, "month": 1},
            output="text",
        ))["result"]
        dashboard, cached = dashboard_service.executive_dashboard(
            dashboard_service.parse_dashboard_filters({
                "filters": {
                    "period": {"type": "year", "year": 2026},
                    "business_unit": "farm",
                }
            })
        )

        self.assertFalse(cached)
        for key in ("total_income", "total_expense", "net_profit", "profit_margin_percent"):
            self.assertEqual(direct[key], wizard[key])
        self.assertEqual(direct["total_income"], dashboard["metrics"]["revenue"])
        self.assertEqual(direct["total_expense"], dashboard["metrics"]["expenses"])
        self.assertEqual(direct["net_profit"], dashboard["metrics"]["net_profit"])
        self.assertEqual(direct["amount_received"], dashboard["metrics"]["sales_received"])
        self.assertEqual(direct["outstanding_amount"], dashboard["metrics"]["outstanding_receivables"])

    @patch("tools.bi_executor.farm_product_ranking")
    @patch("tools.bi_executor.category_summary")
    def test_farm_income_by_category_uses_category_summary_not_product_ranking(
        self,
        category_summary,
        farm_product_ranking,
    ):
        category_summary.return_value = {
            "formula": "category_summary",
            "categories": [{"sector": "Farm", "category": "Seed", "income": 1000}],
        }

        payload = bi_executor.execute_intent(BIIntent(
            business="farm",
            module="income",
            report="income_by_category",
            period={"type": "month", "year": 2026, "month": 7},
            output="pdf",
            categories=["Seed"],
        ))

        category_summary.assert_called_once_with(
            "month:2026-07",
            {"sector": "Farm", "income_expense": "Income", "categories": ["Seed"]},
        )
        farm_product_ranking.assert_not_called()
        self.assertEqual("category_summary", payload["result"]["formula"])

    @patch("tools.bi_executor.sotephwar_product_ranking")
    @patch("tools.bi_executor.category_summary")
    def test_sotephwar_income_by_category_uses_category_summary_not_product_ranking(
        self,
        category_summary,
        sotephwar_product_ranking,
    ):
        category_summary.return_value = {
            "formula": "category_summary",
            "categories": [{"sector": "Sote Phwar", "category": "Retail", "income": 2000}],
        }

        payload = bi_executor.execute_intent(BIIntent(
            business="sote_phwar",
            module="income",
            report="income_by_category",
            period={"type": "month", "year": 2026, "month": 7},
            output="pdf",
            categories=["Retail"],
        ))

        category_summary.assert_called_once_with(
            "month:2026-07",
            {"sector": "Sote Phwar", "income_expense": "Income", "categories": ["Retail"]},
        )
        sotephwar_product_ranking.assert_not_called()
        self.assertEqual("category_summary", payload["result"]["formula"])

    @patch("tools.bi_executor.get_income_detail")
    def test_sales_income_detail_uses_shared_income_detail_engine(self, get_income_detail):
        get_income_detail.return_value = {
            "formula": "income_detail",
            "kpis": {"total_income": 1000, "total_received": 700, "outstanding": 300},
            "rows": [],
            "footer": {"total_transactions": 0, "total_income": 1000, "total_received": 700, "outstanding": 300},
        }

        payload = bi_executor.execute_intent(BIIntent(
            business="sote_phwar",
            module="income",
            report="income_detail",
            period={"type": "relative", "value": "this_year"},
            output="pdf",
            customer="Mya Yadanar",
            categories=["1L"],
        ))

        get_income_detail.assert_called_once_with(
            "Sote Phwar",
            "this_year",
            customer="Mya Yadanar",
            category="",
            categories=["1L"],
            limit=200,
        )
        self.assertEqual("income_detail", payload["result"]["formula"])


if __name__ == "__main__":
    unittest.main()
