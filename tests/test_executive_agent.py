import unittest

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
                "tool": "revenue",
                "args": {"period": "this_month"},
                "result": {
                    "formula": "sales_total",
                    "total_sales": 1000000,
                    "amount_received": 800000,
                    "outstanding_amount": 200000,
                },
            }
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
        self.assertIn("Key Findings", answer)
        self.assertIn("Trend Analysis", answer)
        self.assertIn("Risks & Concerns", answer)
        self.assertIn("Opportunities", answer)
        self.assertIn("Recommendations", answer)
        self.assertIn("Supporting Data", answer)
        self.assertNotIn("SELECT *", answer)


if __name__ == "__main__":
    unittest.main()
