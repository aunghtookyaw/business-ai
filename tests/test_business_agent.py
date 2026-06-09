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

    def test_sotephwar_income_routes_to_table_summary_without_transection_word(self):
        self.assertEqual(
            "sotephwar_transection_summary",
            business_agent.choose_formula("sote phwar income this month"),
        )

    def test_sotephwar_month_by_month_income_routes_to_monthly_summary(self):
        self.assertEqual(
            "sotephwar_transection_monthly_summary",
            business_agent.choose_formula("month by month sote phwar imcome from Jan to now"),
        )

    def test_sotephwar_voucher_payment_routes_to_update(self):
        self.assertEqual(
            "sotephwar_payment_update",
            business_agent.choose_formula("Sote Phwar voucher number 12 got 400000 kyats"),
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

    def test_sotephwar_inventory_stock_routes_to_inventory_stock(self):
        self.assertEqual(
            "sotephwar_inventory_stock",
            business_agent.choose_formula("Sotephwar inventory stock"),
        )

    def test_sotephwar_item_quantity_routes_to_inventory_stock(self):
        self.assertEqual(
            "sotephwar_inventory_stock",
            business_agent.choose_formula("Sote Phwar 4L quantity"),
        )

    def test_sotephwar_inventory_movement_routes_to_inventory_list(self):
        self.assertEqual(
            "sotephwar_inventory_list",
            business_agent.choose_formula("show Sotephwar inventory movement this month"),
        )

    def test_sotephwar_inventory_production_routes_to_movement_summary(self):
        self.assertEqual(
            "sotephwar_inventory_movement_summary",
            business_agent.choose_formula("Sotephwar inventory production this month"),
        )

    def test_financial_obligation_summary_routes_to_summary(self):
        self.assertEqual(
            "financial_obligation_summary",
            business_agent.choose_formula("financial obligations summary"),
        )

    def test_financial_obligation_due_routes_to_due(self):
        self.assertEqual(
            "financial_obligation_due",
            business_agent.choose_formula("financial obligations due soon"),
        )

    def test_financial_obligation_insert_requires_explicit_start_word(self):
        self.assertEqual(
            "financial_obligation_insert",
            business_agent.choose_formula("add financial obligation creditor A amount 100 next due 2026-07-01"),
        )
        self.assertNotEqual(
            "financial_obligation_insert",
            business_agent.choose_formula("Use this format: add financial obligation creditor A amount 100 next due 2026-07-01"),
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

    def test_full_sotephwar_customer_name_beats_short_aung_match(self):
        original_fetch_all = formula_engine._fetch_all
        formula_engine._fetch_all = lambda sql, params=None: [
            {"customer_name": "Aung"},
            {"customer_name": "Aung Agrochemical"},
            {"customer_name": "Pwint Aung Kyaw POL"},
            {"customer_name": "Pwint Aung Kyaw MDY POL"},
        ]

        try:
            self.assertEqual(
                "Pwint Aung Kyaw POL",
                formula_engine._sotephwar_customer_filter("Pwint Aung Kyaw POL vouchers"),
            )
            self.assertEqual(
                "Pwint Aung Kyaw POL",
                formula_engine._sotephwar_customer_filter("Pwint Aung Kyaw POL vouchers, report"),
            )
        finally:
            formula_engine._fetch_all = original_fetch_all

    def test_broad_sotephwar_customer_search_does_not_guess_aung(self):
        original_fetch_all = formula_engine._fetch_all
        formula_engine._fetch_all = lambda sql, params=None: [
            {"customer_name": "Aung"},
            {"customer_name": "Aung Agrochemical"},
            {"customer_name": "Pwint Aung Kyaw POL"},
        ]

        try:
            match = formula_engine._sotephwar_customer_match("Aung vouchers")
            self.assertEqual("ambiguous", match.confidence)
            self.assertIsNone(formula_engine._sotephwar_customer_filter("Aung vouchers"))
            self.assertIn("Aung", match.candidates)
            self.assertIn("Pwint Aung Kyaw POL", match.candidates)
        finally:
            formula_engine._fetch_all = original_fetch_all

    def test_ambiguous_sotephwar_customer_search_does_not_return_all_vouchers(self):
        original_fetch_all = formula_engine._fetch_all
        formula_engine._fetch_all = lambda sql, params=None: [
            {"customer_name": "Aung"},
            {"customer_name": "Aung Agrochemical"},
            {"customer_name": "Pwint Aung Kyaw POL"},
        ]

        try:
            result = formula_engine.run_formula(
                "sotephwar_transection_customer",
                "Aung vouchers",
            )
        finally:
            formula_engine._fetch_all = original_fetch_all

        self.assertEqual([], result["invoices"])
        self.assertEqual("ambiguous", result["customer_match"]["confidence"])
        self.assertIn("Aung Agrochemical", result["customer_match"]["candidates"])

    def test_ambiguous_voucher_search_routes_to_customer_formula(self):
        original_fetch_all = formula_engine._fetch_all
        formula_engine._fetch_all = lambda sql, params=None: [
            {"customer_name": "Aung"},
            {"customer_name": "Aung Agrochemical"},
            {"customer_name": "Pwint Aung Kyaw POL"},
        ]

        try:
            self.assertEqual(
                "sotephwar_transection_customer",
                business_agent.choose_formula("Aung vouchers"),
            )
        finally:
            formula_engine._fetch_all = original_fetch_all

    def test_ambiguous_sotephwar_customer_answer_lists_possible_matches(self):
        answer = business_agent._fast_answer({
            "formula": "sotephwar_transection_customer",
            "period": "all_time",
            "customer": None,
            "unpaid_only": False,
            "customer_match": {
                "confidence": "ambiguous",
                "query": "aung",
                "candidates": ["Aung", "Aung Agrochemical", "Pwint Aung Kyaw POL"],
            },
            "invoices": [],
        })

        self.assertIn("customer search is too broad", answer)
        self.assertIn("Please use the full customer name", answer)
        self.assertIn("Pwint Aung Kyaw POL", answer)

    def test_sotephwar_customer_search_handles_pol_punctuation(self):
        original_fetch_all = formula_engine._fetch_all
        formula_engine._fetch_all = lambda sql, params=None: [
            {"customer_name": "Aung"},
            {"customer_name": "Pwint Aung Kyaw POL"},
        ]

        try:
            match = formula_engine._sotephwar_customer_match("Pwint Aung Kyaw P.O.L vouchers")
            self.assertTrue(match.safe)
            self.assertEqual("Pwint Aung Kyaw POL", match.value)
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
        self.assertEqual(50, captured["params"]["limit"])

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

    def test_sotephwar_monthly_summary_uses_this_year_for_jan_to_now(self):
        captured = {}
        original_fetch_all = formula_engine._fetch_all

        def fake_fetch_all(sql, params=None):
            captured["sql"] = sql
            captured["params"] = params
            return [
                {
                    "month": "2026-01",
                    "invoice_count": 2,
                    "total_amount": 1000,
                    "amount_received": 800,
                    "outstanding_amount": 200,
                },
            ]

        formula_engine._fetch_all = fake_fetch_all
        try:
            result = formula_engine.run_formula(
                "sotephwar_transection_monthly_summary",
                "month by month sote phwar income from Jan to now",
            )
        finally:
            formula_engine._fetch_all = original_fetch_all

        self.assertEqual("this_year", result["period"])
        self.assertIn("DATE_TRUNC('month', \"Invoice_Date\")", captured["sql"])
        self.assertIn("start", captured["params"])
        self.assertEqual(1000, result["months"][0]["total_amount"])

    def test_sotephwar_monthly_summary_answer_lists_month_rows(self):
        answer = business_agent._fast_answer({
            "formula": "sotephwar_transection_monthly_summary",
            "period": "this_year",
            "months": [
                {
                    "month": "2026-01",
                    "invoice_count": 2,
                    "total_amount": 1000,
                    "amount_received": 800,
                    "outstanding_amount": 200,
                },
            ],
        })

        self.assertIn("Sotephwar_Transection month-by-month income for this year", answer)
        self.assertIn("2026-01: total 1,000, received 800, outstanding 200, invoices 2", answer)

    def test_sotephwar_inventory_stock_answer_lists_store_product_stock(self):
        answer = business_agent._fast_answer({
            "formula": "sotephwar_inventory_stock",
            "period": "all_time",
            "store": None,
            "product": None,
            "stock": [
                {
                    "store": "Factory",
                    "product": "Sote Phwar 1L",
                    "stock_qty": 50000,
                },
            ],
        })

        self.assertIn("Sotephwar_Inventory current stock", answer)
        self.assertIn("Factory / Sote Phwar 1L: 50,000", answer)

    def test_financial_obligation_summary_answer_lists_category_status(self):
        answer = business_agent._fast_answer({
            "formula": "financial_obligation_summary",
            "period": "all_time",
            "category": None,
            "status": None,
            "summary": [
                {
                    "category": "Loan",
                    "status": "Active",
                    "amount": 24000000,
                    "obligation_count": 3,
                    "next_due_date": "2026-06-09",
                },
            ],
        })

        self.assertIn("Financial_Obligations summary", answer)
        self.assertIn("Loan / Active: 24,000,000", answer)

    def test_financial_obligation_insert_missing_fields_returns_template(self):
        answer = business_agent._fast_answer({
            "formula": "financial_obligation_insert",
            "period": "all_time",
            "inserted": False,
            "missing": ["creditor", "amount"],
            "values": {},
        })

        self.assertIn("Financial obligation was not inserted", answer)
        self.assertIn("Missing: creditor, amount", answer)

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

    def test_sotephwar_payment_update_adds_received_amount_and_date_note(self):
        captured = {}
        original_fetch_all = formula_engine._fetch_all

        def fake_fetch_all(sql, params=None):
            captured["sql"] = sql
            captured["params"] = params
            return [
                {
                    "id": 1,
                    "invoice_date": "2026-06-01",
                    "invoice_number": "12",
                    "customer_name": "Aye Aye",
                    "item": "Sote Phwar 4L",
                    "note": "Received 2026-06-06: 400,000 kyats",
                    "quantity": 2,
                    "total_amount": 1000000,
                    "previous_amount_received": 100000,
                    "amount_received": 500000,
                    "outstanding_amount": 500000,
                },
            ]

        formula_engine._fetch_all = fake_fetch_all
        try:
            result = formula_engine.run_formula(
                "sotephwar_payment_update",
                "Sote Phwar voucher number 12 got 400,000 kyats received date 2026-06-06",
            )
        finally:
            formula_engine._fetch_all = original_fetch_all

        self.assertTrue(result["updated"])
        self.assertEqual("12", result["invoice_number"])
        self.assertEqual(400000, result["payment_amount"])
        self.assertEqual("2026-06-06", result["received_date"])
        self.assertEqual("12", captured["params"]["invoice_number"])
        self.assertEqual(400000, captured["params"]["amount"])
        self.assertIn('"Amount_Received" = matched.previous_amount_received + %(amount)s', captured["sql"])
        self.assertIn('"Note" = TRIM', captured["sql"])

    def test_sotephwar_payment_update_answer_shows_received_table(self):
        answer = business_agent._fast_answer({
            "formula": "sotephwar_payment_update",
            "updated": True,
            "invoice_number": "12",
            "payment_amount": 400000,
            "received_date": "2026-06-06",
            "invoices": [
                {
                    "invoice_date": "2026-06-01",
                    "customer_name": "Aye Aye",
                    "item": "Sote Phwar 4L",
                    "total_amount": 1000000,
                    "previous_amount_received": 100000,
                    "amount_received": 500000,
                    "outstanding_amount": 500000,
                    "note": "Received 2026-06-06: 400,000 kyats",
                },
            ],
        })

        self.assertIn("Sote Phwar payment updated", answer)
        self.assertIn("Voucher: 12", answer)
        self.assertIn("Received now: 500,000", answer)
        self.assertIn("Note: Received 2026-06-06: 400,000 kyats", answer)

    def test_sotephwar_transection_4l_item_filter(self):
        self.assertEqual(
            "Sote Phwar 4L",
            formula_engine._sotephwar_item_filter("how much 4L bottles sell"),
        )

    def test_sotephwar_100ml_item_filter(self):
        self.assertEqual(
            "Sote Phwar 100 mL",
            formula_engine._sotephwar_item_filter("Sote Phwar 100 mL quantity"),
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

    def test_multiple_category_filter_uses_in_clause(self):
        sql, params = formula_engine._dimension_filter({
            "income_expense": "Expense",
            "categories": ["Makro Expense", "Farm/Wages and salary"],
        })

        self.assertIn('"Categorization" IN (%(category_0)s, %(category_1)s)', sql)
        self.assertEqual("Makro Expense", params["category_0"])
        self.assertEqual("Farm/Wages and salary", params["category_1"])
        self.assertEqual("Expense", params["income_expense"])

    def test_sotephwar_sector_filter_uses_sotephwar_only(self):
        from tools.bi_executor import _filters
        from tools.bi_intents import BIIntent

        filters = _filters(
            BIIntent(business="sote_phwar", module="expense", report="expense_detail"),
            "Expense",
        )

        self.assertEqual(
            {"sector": "Sote Phwar", "income_expense": "Expense"},
            filters,
        )

    def test_category_summary_returns_totals(self):
        original_fetch_all = formula_engine._fetch_all
        formula_engine._fetch_all = lambda sql, params=None: [
            {
                "sector": "Sote Phwar",
                "category": "Packaging",
                "income": 0,
                "expense": 700,
                "transaction_count": 2,
            },
            {
                "sector": "Sote Phwar",
                "category": "Delivery",
                "income": 0,
                "expense": 300,
                "transaction_count": 1,
            },
        ]
        try:
            result = formula_engine.category_summary("this_month", {"sector": "Sote Phwar", "income_expense": "Expense"})

            self.assertEqual(0, result["total_income"])
            self.assertEqual(1000, result["total_expense"])
            self.assertEqual(-1000, result["net_total"])
            self.assertEqual(3, result["transaction_count"])
        finally:
            formula_engine._fetch_all = original_fetch_all

    def test_bi_sotephwar_kpi_uses_sotephwar_transection_income(self):
        from tools import bi_executor
        from tools.bi_intents import BIIntent

        original_sotephwar_summary = bi_executor.sotephwar_transection_summary
        original_expense_total = bi_executor.expense_total
        seen = []

        bi_executor.sotephwar_transection_summary = lambda period: {
            "formula": "sotephwar_transection_summary",
            "period": period,
            "invoice_count": 2,
            "total_amount": 1000,
            "amount_received": 800,
            "outstanding_amount": 200,
        }

        def fake_expense_total(period, filters=None):
            seen.append(filters)
            return {
                "formula": "expense_total",
                "period": period,
                "total_expense": 300,
                "expense_count": 4,
            }

        bi_executor.expense_total = fake_expense_total
        try:
            payload = bi_executor.execute_intent(BIIntent(
                business="sote_phwar",
                module="kpi",
                report="kpi",
                period={"type": "relative", "value": "this_month"},
                output="text",
            ))

            result = payload["result"]
            self.assertEqual(1000, result["total_income"])
            self.assertEqual(300, result["total_expense"])
            self.assertEqual(700, result["net_profit"])
            self.assertEqual({"sector": "Sote Phwar", "income_expense": "Expense"}, seen[0])
            self.assertEqual(1000, result["sources"]["sotephwar_transection_total_amount"])
        finally:
            bi_executor.sotephwar_transection_summary = original_sotephwar_summary
            bi_executor.expense_total = original_expense_total

    def test_bi_sotephwar_cash_flow_uses_received_amount(self):
        from tools import bi_executor
        from tools.bi_intents import BIIntent

        original_sotephwar_summary = bi_executor.sotephwar_transection_summary
        original_cash_flow = bi_executor.cash_flow

        bi_executor.sotephwar_transection_summary = lambda period: {
            "formula": "sotephwar_transection_summary",
            "period": period,
            "invoice_count": 2,
            "total_amount": 1000,
            "amount_received": 800,
            "outstanding_amount": 200,
        }
        bi_executor.cash_flow = lambda period, filters=None: {
            "formula": "cash_flow",
            "period": period,
            "total_inflow": 0,
            "total_outflow": 300,
            "net_cash_flow": -300,
            "by_payment_method": [
                {"payment_method": "Cash", "inflow": 0, "outflow": 300, "net_cash_flow": -300},
            ],
        }
        try:
            payload = bi_executor.execute_intent(BIIntent(
                business="sote_phwar",
                module="cash_flow",
                report="cash_flow",
                period={"type": "relative", "value": "this_month"},
                output="text",
            ))

            result = payload["result"]
            self.assertEqual(800, result["total_inflow"])
            self.assertEqual(300, result["total_outflow"])
            self.assertEqual(500, result["net_cash_flow"])
            self.assertEqual("Sotephwar_Transection received", result["by_payment_method"][0]["payment_method"])
        finally:
            bi_executor.sotephwar_transection_summary = original_sotephwar_summary
            bi_executor.cash_flow = original_cash_flow

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
                {
                    "category": "Factory 2 Set up cost",
                    "transaction_text_search": {
                        "category": "factory 2 setup cost",
                        "note": "factory 2 setup",
                    },
                },
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
        self.assertIn('REPLACE(LOWER(COALESCE("Categorization", \'\')), \'set up\', \'setup\') LIKE %(transaction_category_search)s', captured["sql"])
        self.assertIn('REPLACE(LOWER(COALESCE("Note", \'\')), \'set up\', \'setup\') LIKE %(transaction_note_search)s', captured["sql"])
        self.assertEqual("%factory setup cost%", captured["params"]["transaction_category_search"])
        self.assertEqual("%factory setup%", captured["params"]["transaction_note_search"])

    def test_factory_setup_cost_all_time_total_searches_category_item_and_note(self):
        captured = {}
        original_fetch_all = formula_engine._fetch_all
        original_known_dimension_values = formula_engine._known_dimension_values
        original_transaction_column_exists = formula_engine._transaction_column_exists

        def fake_fetch_all(sql, params=None):
            captured["sql"] = sql
            captured["params"] = params
            return [{
                "total_expense": 1200000,
                "expense_count": 3,
                "missing_amount_count": 0,
            }]

        formula_engine._fetch_all = fake_fetch_all
        formula_engine._known_dimension_values = lambda: {
            "income_expenses": [],
            "sectors": [],
            "categories": ["Factory 2 Set up cost"],
            "item_descriptions": [],
            "payment_methods": [],
        }
        formula_engine._transaction_column_exists = lambda column_name: column_name == "Note"
        try:
            result = formula_engine.run_formula(
                "expense_total",
                "all time factory 2 setup cost",
            )
        finally:
            formula_engine._fetch_all = original_fetch_all
            formula_engine._known_dimension_values = original_known_dimension_values
            formula_engine._transaction_column_exists = original_transaction_column_exists

        self.assertEqual("all_time", result["period"])
        self.assertEqual(1200000, result["total_expense"])
        self.assertIn('REPLACE(LOWER(COALESCE("Categorization", \'\')), \'set up\', \'setup\') LIKE %(transaction_category_search)s', captured["sql"])
        self.assertIn('REPLACE(LOWER(COALESCE("Item_Description", \'\')), \'set up\', \'setup\') LIKE %(transaction_note_search)s', captured["sql"])
        self.assertIn('REPLACE(LOWER(COALESCE("Note", \'\')), \'set up\', \'setup\') LIKE %(transaction_note_search)s', captured["sql"])
        self.assertNotIn('AND "Date" >= %(start)s', captured["sql"])
        self.assertEqual("%factory 2 setup cost%", captured["params"]["transaction_category_search"])
        self.assertEqual("%factory 2 setup%", captured["params"]["transaction_note_search"])

    def test_transaction_detail_extracts_free_text_search_terms(self):
        self.assertEqual(
            {
                "transaction_text_search": {
                    "terms": ["toll", "gate"],
                },
            },
            formula_engine.extract_dimension_filters("show expenses for toll gate June 2026 detail"),
        )

    def test_transaction_detail_searches_item_and_comment_without_exact_item_lock(self):
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
            "categories": [],
            "item_descriptions": ["Premium Diesel(1ပေပါ)"],
            "payment_methods": [],
        }
        formula_engine._transaction_column_exists = lambda column_name: column_name == "AI_Comment"
        try:
            result = formula_engine.run_formula(
                "list_transactions",
                "show premium diesel June 2026 detail",
            )
        finally:
            formula_engine._fetch_all = original_fetch_all
            formula_engine._known_dimension_values = original_known_dimension_values
            formula_engine._transaction_column_exists = original_transaction_column_exists

        self.assertEqual("list_transactions", result["formula"])
        self.assertNotIn('AND "Item_Description" = %(item_description)s', captured["sql"])
        self.assertIn('LOWER(COALESCE("Item_Description", \'\')) LIKE %(transaction_text_search_0)s', captured["sql"])
        self.assertIn('LOWER(COALESCE("AI_Comment", \'\')) LIKE %(transaction_text_search_1)s', captured["sql"])
        self.assertEqual("%premium%", captured["params"]["transaction_text_search_0"])
        self.assertEqual("%diesel%", captured["params"]["transaction_text_search_1"])

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
