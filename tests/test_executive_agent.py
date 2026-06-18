import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tools import executive_agent, executive_tools


class ExecutiveAgentTest(unittest.TestCase):
    def test_default_plan_routes_customer_risk_to_top_customers(self):
        plan = executive_tools.build_default_plan("Which customer contributes too much revenue risk?")

        self.assertEqual("top_customers", plan[0]["name"])

    def test_default_plan_routes_revenue_comparison(self):
        plan = executive_tools.build_default_plan("Compare Sote Phwar sales this month versus last month")

        self.assertEqual("comparison", plan[0]["name"])
        self.assertEqual("sote_phwar", plan[0]["args"]["business"])
        self.assertEqual("revenue", plan[0]["args"]["metric"])

    def test_kpi_management_report_uses_full_management_plan(self):
        plan = executive_tools.build_default_plan("Generate a Farm KPI Management Report this month")

        self.assertEqual(
            ["kpi", "revenue", "expense", "cash_flow", "top_customers", "top_expenses", "inventory", "comparison"],
            [step["name"] for step in plan],
        )
        self.assertTrue(all(step["args"]["business"] == "farm" for step in plan))

    def test_plan_validation_rejects_unknown_tools(self):
        plan = executive_tools.validate_plan([
            {"name": "raw_sql", "args": {"sql": "select * from x"}},
            {"name": "kpi", "args": {"period": "this_month"}},
        ])

        self.assertEqual([{"name": "kpi", "args": {"period": "this_month"}}], plan)

    def test_executive_answer_uses_report_format(self):
        original_plan = executive_agent.plan_executive_tools
        original_execute = executive_agent.execute_plan
        original_summary = executive_agent._ai_summary
        executive_agent.plan_executive_tools = lambda question: [{"name": "revenue", "args": {"period": "this_month"}}]
        executive_agent.execute_plan = lambda plan: [
            {
                "tool": "kpi",
                "args": {"period": "this_month"},
                "result": {
                    "formula": "kpi_overview",
                    "total_income": 1000000,
                    "total_expense": 600000,
                    "net_profit": 400000,
                    "profit_margin_percent": 40,
                },
            },
            {
                "tool": "revenue",
                "args": {"period": "this_month"},
                "result": {
                    "formula": "sales_total",
                    "total_sales": 1000000,
                    "amount_received": 800000,
                    "outstanding_amount": 200000,
                },
            },
            {
                "tool": "comparison",
                "args": {"period": "this_month", "metric": "revenue"},
                "result": {
                    "formula": "comparison",
                    "metric": "revenue",
                    "current": {"total_sales": 1000000},
                    "previous": {"total_sales": 900000},
                },
            },
        ]
        executive_agent._ai_summary = lambda question, tool_results: None
        try:
            answer = executive_agent.answer_executive_question("Analyze revenue")
        finally:
            executive_agent.plan_executive_tools = original_plan
            executive_agent.execute_plan = original_execute
            executive_agent._ai_summary = original_summary

        self.assertIn("BigShot Intelligence Report", answer)
        self.assertIn("Executive Summary", answer)
        self.assertIn("KPI Dashboard", answer)
        self.assertIn("| KPI | Current | Previous | Change % | Trend |", answer)
        self.assertIn("Key Findings", answer)
        self.assertIn("Revenue Analysis", answer)
        self.assertIn("Expense Analysis", answer)
        self.assertIn("Profitability Analysis", answer)
        self.assertIn("Customer Analysis", answer)
        self.assertIn("Inventory Analysis", answer)
        self.assertIn("Business Growth Analysis", answer)
        self.assertIn("Trend Analysis", answer)
        self.assertIn("Risk Analysis / Risks & Concerns", answer)
        self.assertIn("Opportunities", answer)
        self.assertIn("Recommendations", answer)
        self.assertIn("Immediate Actions", answer)
        self.assertIn("Management Conclusion", answer)
        self.assertIn("Supporting Data", answer)
        self.assertIn("What this means for BigShot", answer)
        self.assertNotIn("SELECT *", answer)

    def test_executive_prompt_contains_cfo_rules(self):
        self.assertIn("Chief Financial Officer", executive_agent.EXECUTIVE_ROLE_PROMPT)
        self.assertIn("customer outstanding", executive_agent.EXECUTIVE_ROLE_PROMPT)
        self.assertIn("Potential Data Quality Issue Detected", executive_agent.EXECUTIVE_ROLE_PROMPT)
        self.assertIn("What does this mean for BigShot and what should management do next", executive_agent.EXECUTIVE_ROLE_PROMPT)

    def test_loads_kpi_framework_from_knowledge_file(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "bigshot_kpi_framework.md"
            path.write_text("Cash Flow\nProfitability\n", encoding="utf-8")

            self.assertEqual("Cash Flow\nProfitability", executive_agent.load_kpi_framework(path))

    def test_missing_kpi_framework_returns_empty_string(self):
        self.assertEqual("", executive_agent.load_kpi_framework(Path("/missing/kpi.md")))

    def test_summary_prompt_places_kpi_rules_before_report_data(self):
        prompt = executive_agent.build_executive_summary_prompt(
            "Analyze revenue",
            [{"tool": "revenue", "result": {"total_sales": 1000}}],
            kpi_rules="KPI RULES",
        )

        self.assertLess(prompt.index("KPI RULES"), prompt.index("Analyze the following data:"))
        self.assertIn('"total_sales": 1000', prompt)
        self.assertIn("What does this mean for BigShot and what should management do next", prompt)


if __name__ == "__main__":
    unittest.main()
