import unittest

import business_agent
from tools import formula_engine


class BusinessAgentRoutingTest(unittest.TestCase):
    def test_machinary_equipment_routes_to_category_summary(self):
        self.assertEqual(
            "category_summary",
            business_agent.choose_formula("what category is machinary equipment"),
        )

    def test_category_question_routes_to_category_summary(self):
        self.assertEqual(
            "category_summary",
            business_agent.choose_formula("show category summary this month"),
        )

    def test_top_numbered_expense_question_routes_to_top_expenses(self):
        self.assertEqual(
            "top_expenses",
            business_agent.choose_formula("show top 4 expense"),
        )

    def test_highest_expense_question_routes_to_top_expenses(self):
        self.assertEqual(
            "top_expenses",
            business_agent.choose_formula("top 10 highest expenses"),
        )

    def test_top_numbered_income_question_routes_to_top_income(self):
        self.assertEqual(
            "top_income",
            business_agent.choose_formula("show top 10 income"),
        )

    def test_top_sales_question_routes_to_top_income(self):
        self.assertEqual(
            "top_income",
            business_agent.choose_formula("top 4 sales"),
        )

    def test_top_sector_income_question_routes_to_top_income(self):
        self.assertEqual(
            "top_income",
            business_agent.choose_formula("top 5 sote phwar income"),
        )

    def test_machinery_cost_routes_to_expense_total(self):
        self.assertEqual(
            "expense_total",
            business_agent.choose_formula("machinery equipment and maintenance cost"),
        )

    def test_category_cost_detail_routes_to_transaction_list(self):
        self.assertEqual(
            "list_transactions",
            business_agent.choose_formula("Factory setup cost May 2026 detail"),
        )

    def test_top_machinery_cost_routes_to_top_expenses(self):
        self.assertEqual(
            "top_expenses",
            business_agent.choose_formula("top 5 machinery equipment and maintenance cost"),
        )

    def test_specific_date_transaction_routes_to_transaction_list(self):
        self.assertEqual(
            "list_transactions",
            business_agent.choose_formula("show transection on 2026-05-13"),
        )

    def test_sotephwar_transection_summary_routes_to_table_summary(self):
        self.assertEqual(
            "sotephwar_transection_summary",
            business_agent.choose_formula("total in sotephwar transection"),
        )

    def test_sotephwar_transection_analyze_stays_on_table(self):
        self.assertEqual(
            "sotephwar_transection_summary",
            business_agent.choose_formula("analyze in sotephwar transection"),
        )

    def test_sotephwar_transection_top_routes_to_table_top(self):
        self.assertEqual(
            "sotephwar_transection_top",
            business_agent.choose_formula("top 5 in sotephwar transection"),
        )

    def test_sotephwar_transection_date_routes_to_table_list(self):
        self.assertEqual(
            "sotephwar_transection_list",
            business_agent.choose_formula("show invoice on 2026-05-13 in sotephwar transection"),
        )

    def test_sotephwar_transection_quantity_routes_to_table_quantity(self):
        self.assertEqual(
            "sotephwar_transection_quantity",
            business_agent.choose_formula("how much 4L bottles sell in may 2026 in sotephwar transection"),
        )

    def test_sotephwar_customer_transaction_routes_to_customer_vouchers(self):
        self.assertEqual(
            "sotephwar_transection_customer",
            business_agent.choose_formula("please tell me the transection of Pwint Aung Kyaw"),
        )

    def test_partial_sotephwar_customer_name_is_detected(self):
        original_fetch_all = formula_engine._fetch_all
        formula_engine._fetch_all = lambda sql, params=None: [
            {"customer_name": "Pwint Aung Kyaw POL"},
            {"customer_name": "Myat Nyi Aung, Ko"},
        ]

        try:
            self.assertEqual(
                "Pwint Aung Kyaw POL",
                formula_engine._sotephwar_customer_filter("show Sote Phwar vouchers for Pwint Aung Kyaw"),
            )
        finally:
            formula_engine._fetch_all = original_fetch_all

    def test_partial_sotephwar_customer_name_ignores_month_words(self):
        original_fetch_all = formula_engine._fetch_all
        formula_engine._fetch_all = lambda sql, params=None: [
            {"customer_name": "Pwint Aung Kyaw POL"},
            {"customer_name": "Myat Nyi Aung, Ko"},
        ]

        try:
            self.assertEqual(
                "Pwint Aung Kyaw POL",
                formula_engine._sotephwar_customer_filter("show Sote Phwar vouchers for Pwint Aung Kyaw in June"),
            )
        finally:
            formula_engine._fetch_all = original_fetch_all

    def test_unpaid_sotephwar_vouchers_route_to_customer_vouchers(self):
        self.assertEqual(
            "sotephwar_transection_customer",
            business_agent.choose_formula("Show unpaid Sote Phwar vouchers by customer"),
        )

    def test_unpaid_sotephwar_vouchers_filter_to_outstanding_only(self):
        captured = {}
        original_fetch_all = formula_engine._fetch_all

        def fake_fetch_all(sql, params=None):
            captured["sql"] = sql
            captured["params"] = params
            return []

        formula_engine._fetch_all = fake_fetch_all
        try:
            result = formula_engine.run_formula(
                "sotephwar_transection_customer",
                "Show unpaid Sote Phwar vouchers by customer",
            )
        finally:
            formula_engine._fetch_all = original_fetch_all

        self.assertTrue(result["unpaid_only"])
        self.assertIn(
            'COALESCE("Total_Amount", 0) - COALESCE("Amount_Received", 0) > 0',
            captured["sql"],
        )
        self.assertIn('COALESCE("Note", \'\') AS note', captured["sql"])

    def test_sotephwar_voucher_answer_includes_note_when_available(self):
        answer = business_agent._fast_answer({
            "formula": "sotephwar_transection_customer",
            "period": "all_time",
            "customer": "Aye Aye",
            "unpaid_only": True,
            "invoices": [
                {
                    "invoice_date": "2026-05-13",
                    "invoice_number": "V-001",
                    "customer_name": "Aye Aye",
                    "item": "Sote Phwar 4L",
                    "quantity": 2,
                    "total_amount": 10000,
                    "amount_received": 4000,
                    "outstanding_amount": 6000,
                    "note": "Call before delivery",
                },
            ],
        })

        self.assertIn("Note: Call before delivery", answer)

    def test_sotephwar_voucher_answer_shows_empty_note_when_requested(self):
        answer = business_agent._fast_answer({
            "formula": "sotephwar_transection_customer",
            "period": "all_time",
            "customer": "Pwint Aung Kyaw",
            "unpaid_only": False,
            "include_note": True,
            "invoices": [
                {
                    "invoice_date": "2026-05-27",
                    "invoice_number": "80",
                    "customer_name": "Pwint Aung Kyaw POL",
                    "item": "Sote Phwar 1L",
                    "quantity": 1000,
                    "total_amount": 30000000,
                    "amount_received": 0,
                    "outstanding_amount": 30000000,
                    "note": "",
                },
            ],
        })

        self.assertIn("Note: -", answer)

    def test_sotephwar_voucher_search_filters_invoice_numbers(self):
        captured = {}
        original_fetch_all = formula_engine._fetch_all

        def fake_fetch_all(sql, params=None):
            captured["sql"] = sql
            captured["params"] = params
            return []

        formula_engine._fetch_all = fake_fetch_all
        try:
            result = formula_engine.run_formula(
                "sotephwar_transection_customer",
                "show Sote Phwar voucher 12 and invoice 13",
            )
        finally:
            formula_engine._fetch_all = original_fetch_all

        self.assertEqual(["12", "13"], result["invoice_numbers"])
        self.assertEqual(["12", "13"], captured["params"]["invoice_numbers"])
        self.assertIn('"Invoice_Number"::text = ANY(%(invoice_numbers)s)', captured["sql"])

    def test_sotephwar_transection_4l_item_filter(self):
        self.assertEqual(
            "Sote Phwar 4L",
            formula_engine._sotephwar_item_filter("how much 4L bottles sell"),
        )

    def test_suggestion_question_routes_to_analysis(self):
        self.assertEqual(
            "analysis",
            business_agent.choose_formula("please give me comment and suggestion"),
        )

    def test_analyze_data_routes_to_analysis(self):
        self.assertEqual(
            "analysis",
            business_agent.choose_formula("analyze the data"),
        )

    def test_analysis_fallback_is_commentary_not_raw_json(self):
        answer = business_agent._fallback_analysis_answer({
            "kpi": {
                "total_income": 100,
                "total_expense": 150,
                "net_profit": -50,
                "profit_margin_percent": -50,
            },
            "cash_flow": {
                "by_payment_method": [
                    {"payment_method": "By Cash", "net_cash_flow": -80},
                ],
            },
            "category_summary": {
                "categories": [
                    {"category": "Wages", "expense": 70},
                    {"category": "Fuel", "expense": 30},
                ],
            },
            "top_expenses": {
                "expenses": [
                    {"item": "Salary", "amount": 70},
                ],
            },
        })

        self.assertIn("Comment:", answer)
        self.assertIn("Recommended actions:", answer)
        self.assertNotIn('"kpi"', answer)

    def test_combined_kpi_uses_sotephwar_transection_without_double_counting(self):
        result = business_agent._combined_kpi(
            "month:2026-05",
            {
                "total_income": 1_000,
                "total_expense": 400,
            },
            {
                "sectors": [
                    {"sector": "Farm", "income": 300, "expense": 100},
                    {"sector": "Sote Phwar", "income": 200, "expense": 0},
                ],
            },
            {
                "total_amount": 500,
            },
        )

        self.assertEqual(1_300, result["total_income"])
        self.assertEqual(400, result["total_expense"])
        self.assertEqual(900, result["net_profit"])
        self.assertEqual(
            800,
            result["sources"]["transection_income_excluding_sotephwar"],
        )
        self.assertEqual(
            500,
            result["sources"]["sotephwar_transection_total_amount"],
        )

    def test_top_limit_is_extracted_from_question(self):
        self.assertEqual(
            4,
            formula_engine.extract_top_limit("show top 4 expense"),
        )

    def test_top_limit_defaults_to_five(self):
        self.assertEqual(
            5,
            formula_engine.extract_top_limit("show top expenses"),
        )

    def test_subgroup_question_routes_to_category_summary(self):
        self.assertEqual(
            "category_summary",
            business_agent.choose_formula("show transection group by subgroup"),
        )

    def test_farm_filter_is_detected(self):
        filters = formula_engine.extract_dimension_filters("show farm expense this month")
        self.assertEqual("Farm", filters["sector"])
        self.assertEqual("Expense", filters["income_expense"])

    def test_machinery_category_filter_is_detected(self):
        self.assertEqual(
            {"category": "Machinery equipment and maintenance"},
            formula_engine.extract_dimension_filters("machinery equipment and maintenance cost"),
        )

    def test_factory_setup_cost_detail_filters_category_and_expense(self):
        formula_engine.clear_dimension_value_cache()
        original_fetch_one = formula_engine._fetch_one
        formula_engine._fetch_one = lambda sql, params=None: {
            "income_expenses": [],
            "sectors": [],
            "categories": ["Factory 2 Set up cost"],
            "item_descriptions": [],
            "payment_methods": [],
        }

        try:
            self.assertEqual(
                {"category": "Factory 2 Set up cost"},
                formula_engine.extract_dimension_filters("Factory setup cost May 2026 detail"),
            )
        finally:
            formula_engine._fetch_one = original_fetch_one
            formula_engine.clear_dimension_value_cache()

    def test_factory_setup_cost_detail_query_lists_transaction_rows(self):
        captured = {}
        original_fetch_all = formula_engine._fetch_all
        original_known_dimension_values = formula_engine._known_dimension_values
        original_transaction_column_exists = formula_engine._transaction_column_exists

        def fake_fetch_all(sql, params=None):
            captured["sql"] = sql
            captured["params"] = params
            return []

        formula_engine._fetch_all = fake_fetch_all
        formula_engine._known_dimension_values = lambda: {
            "income_expenses": [],
            "sectors": [],
            "categories": ["Factory setup cost"],
            "item_descriptions": [],
            "payment_methods": [],
        }
        formula_engine._transaction_column_exists = lambda column_name: column_name == "Note"
        try:
            result = formula_engine.run_formula(
                "list_transactions",
                "Factory setup cost May 2026 detail",
            )
        finally:
            formula_engine._fetch_all = original_fetch_all
            formula_engine._known_dimension_values = original_known_dimension_values
            formula_engine._transaction_column_exists = original_transaction_column_exists

        self.assertEqual("list_transactions", result["formula"])
        self.assertEqual("month:2026-05", result["period"])
        self.assertIn('COALESCE("Note", \'\') AS note', captured["sql"])
        self.assertIn('AND "Income_Expense" = %(income_expense)s', captured["sql"])
        self.assertIn('AND "Categorization" = %(category)s', captured["sql"])

    def test_transaction_detail_answer_shows_each_line_with_note(self):
        answer = business_agent._fast_answer({
            "formula": "list_transactions",
            "period": "month:2026-05",
            "filters": {
                "category": "Factory setup cost",
                "income_expense": "Expense",
            },
            "transactions": [
                {
                    "id": 12,
                    "Date": "2026-05-04",
                    "income_expense": "Expense",
                    "category": "Factory setup cost",
                    "item": "Wiring",
                    "amount": 500000,
                    "payment_method": "Cash",
                    "note": "Factory meter setup",
                },
            ],
        })

        self.assertIn("Transactions for May 2026 (Factory setup cost / Expense)", answer)
        self.assertIn("Transaction 12", answer)
        self.assertIn("Amount: 500,000", answer)
        self.assertIn("Note: Factory meter setup", answer)

    def test_exact_iso_date_is_detected(self):
        self.assertEqual(
            "date:2026-05-13",
            formula_engine.normalize_period("expense on 2026-05-13"),
        )

    def test_exact_slash_date_is_detected(self):
        self.assertEqual(
            "date:2026-05-13",
            formula_engine.normalize_period("expense on 13/5/2026"),
        )

    def test_common_misspelled_month_is_detected(self):
        self.assertEqual(
            "month:2026-02",
            formula_engine.normalize_period("top expense in Febuary 2026"),
        )

    def test_common_misspelled_month_date_is_detected(self):
        self.assertEqual(
            "date:2026-02-03",
            formula_engine.normalize_period("expense on Febuary 3 2026"),
        )

    def test_no_date_defaults_to_all_time(self):
        self.assertEqual(
            "all_time",
            formula_engine.normalize_period("show Sote Phwar vouchers for Pwint Aung Kyaw"),
        )

    def test_extension_agrochemical_filters_are_detected(self):
        filters = formula_engine.extract_dimension_filters("extension agrochemical expense")
        self.assertEqual("SP Extension", filters["sector"])
        self.assertEqual("Agrochemical", filters["category"])
        self.assertEqual("Expense", filters["income_expense"])

    def test_sotephwar_filter_maps_to_sote_phwar(self):
        self.assertEqual(
            {"sector": "Sote Phwar"},
            formula_engine.extract_dimension_filters("sotephwar profit"),
        )

    def test_dynamic_sector_filter_is_detected_from_database_values(self):
        formula_engine.clear_dimension_value_cache()
        original_fetch_one = formula_engine._fetch_one
        formula_engine._fetch_one = lambda sql, params=None: {
            "income_expenses": [],
            "sectors": ["Retail Shop"],
            "categories": [],
            "item_descriptions": [],
            "payment_methods": [],
        }

        try:
            self.assertEqual(
                {"sector": "Retail Shop"},
                formula_engine.extract_dimension_filters("retail shop sales this month"),
            )
        finally:
            formula_engine._fetch_one = original_fetch_one
            formula_engine.clear_dimension_value_cache()

    def test_dynamic_category_filter_is_detected_from_database_values(self):
        formula_engine.clear_dimension_value_cache()
        original_fetch_one = formula_engine._fetch_one
        formula_engine._fetch_one = lambda sql, params=None: {
            "income_expenses": [],
            "sectors": [],
            "categories": ["Seed & Fertilizer"],
            "item_descriptions": [],
            "payment_methods": [],
        }

        try:
            self.assertEqual(
                {"category": "Seed & Fertilizer", "income_expense": "Expense"},
                formula_engine.extract_dimension_filters("seed fertilizer expense this month"),
            )
        finally:
            formula_engine._fetch_one = original_fetch_one
            formula_engine.clear_dimension_value_cache()

    def test_dynamic_item_description_filter_is_detected_from_database_values(self):
        formula_engine.clear_dimension_value_cache()
        original_fetch_one = formula_engine._fetch_one
        formula_engine._fetch_one = lambda sql, params=None: {
            "income_expenses": [],
            "sectors": [],
            "categories": [],
            "item_descriptions": ["Diesel Fuel"],
            "payment_methods": [],
        }

        try:
            self.assertEqual(
                {"item_description": "Diesel Fuel", "income_expense": "Expense"},
                formula_engine.extract_dimension_filters("diesel fuel expense this month"),
            )
        finally:
            formula_engine._fetch_one = original_fetch_one
            formula_engine.clear_dimension_value_cache()

    def test_dynamic_payment_method_filter_is_detected_from_database_values(self):
        formula_engine.clear_dimension_value_cache()
        original_fetch_one = formula_engine._fetch_one
        formula_engine._fetch_one = lambda sql, params=None: {
            "income_expenses": [],
            "sectors": [],
            "categories": [],
            "item_descriptions": [],
            "payment_methods": ["M-Pay"],
        }

        try:
            self.assertEqual(
                {"payment_method": "M-Pay", "income_expense": "Expense"},
                formula_engine.extract_dimension_filters("m pay expense this month"),
            )
        finally:
            formula_engine._fetch_one = original_fetch_one
            formula_engine.clear_dimension_value_cache()


if __name__ == "__main__":
    unittest.main()
