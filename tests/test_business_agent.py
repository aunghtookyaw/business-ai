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

    def test_top_customers_routes_to_top_income(self):
        self.assertEqual(
            "top_income",
            business_agent.choose_formula("top customers this year"),
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

    def test_payment_receive_insert_routes_to_append_only_table(self):
        self.assertEqual(
            "payment_receive_insert",
            business_agent.choose_formula("receive payment sector Farm voucher 123 amount 50000 method Cash"),
        )

    def test_payment_receivable_kpis_route_to_summary_before_analysis(self):
        self.assertEqual(
            "payment_receive_summary",
            business_agent.choose_formula("outstanding receivables aging analysis"),
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
        self.assertIn('cust."customer_name"', captured["sql"])
        self.assertIn('s."Customer_Name"', captured["sql"])
        self.assertIn('COALESCE(s."Note", \'\') AS note', captured["sql"])
        self.assertEqual(50, captured["params"]["limit"])

    def test_sotephwar_voucher_pdf_uses_two_hundred_limit(self):
        captured = {}
        original_fetch_all = formula_engine._fetch_all

        def fake_fetch_all(sql, params=None):
            captured["sql"] = sql
            captured["params"] = params
            return []

        formula_engine._fetch_all = fake_fetch_all
        try:
            formula_engine.run_formula(
                "sotephwar_transection_customer",
                "Show unpaid Sote Phwar vouchers by customer send pdf",
            )
        finally:
            formula_engine._fetch_all = original_fetch_all

        self.assertEqual(200, captured["params"]["limit"])

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

    def test_payment_receive_parser_extracts_required_fields(self):
        values = formula_engine._parse_payment_receive(
            "receive payment sector Sote Phwar voucher INV-12 amount 400,000 method Cash ref R1 notes partial recorded by Admin"
        )

        self.assertEqual("Sote Phwar", values["sector"])
        self.assertEqual("INV-12", values["voucher_number"])
        self.assertEqual(400000, values["receive_amount"])
        self.assertEqual("Cash", values["payment_method"])
        self.assertEqual("R1", values["reference_number"])
        self.assertEqual("partial", values["notes"])
        self.assertEqual("Admin", values["recorded_by"])

    def test_payment_receive_insert_updates_voucher_summary_without_invoice_totals(self):
        captured = {"sql": []}
        original_execute = formula_engine._execute
        original_fetch_one = formula_engine._fetch_one

        def fake_execute(sql, params=None):
            captured["sql"].append(sql)
            captured.setdefault("execute_params", []).append(params)

        def fake_fetch_one(sql, params=None):
            captured["sql"].append(sql)
            captured["params"] = params
            if "FROM" in sql and "farm_transection" in sql:
                return {
                    "sector": "Farm",
                    "voucher_number": "123",
                    "invoice_date": "2026-06-01",
                    "customer": "Aye Aye",
                    "invoice_amount": 1000000,
                }
            if "INSERT INTO" in sql:
                return {
                    "id": 1,
                    "receive_date": "2026-06-20",
                    "sector": params["sector"],
                    "voucher_number": params["voucher_number"],
                    "customer": params["customer"],
                    "invoice_amount": params["invoice_amount"],
                    "previous_paid": params["previous_paid"],
                    "receive_amount": params["receive_amount"],
                    "outstanding_balance": params["outstanding_balance"],
                    "payment_method": params["payment_method"],
                    "reference_number": params["reference_number"],
                    "notes": params["notes"],
                    "recorded_by": params["recorded_by"],
                }
            if "AS previous_paid" in sql:
                return {"previous_paid": 200000}
            if "AS total_received" in sql:
                return {"total_received": 500000}
            return {}

        formula_engine._execute = fake_execute
        formula_engine._fetch_one = fake_fetch_one
        try:
            result = formula_engine.run_formula(
                "payment_receive_insert",
                "receive payment sector Farm voucher 123 amount 300000 method Cash",
            )
        finally:
            formula_engine._execute = original_execute
            formula_engine._fetch_one = original_fetch_one

        self.assertTrue(result["inserted"])
        self.assertEqual(200000, result["payment"]["previous_paid"])
        self.assertEqual(300000, result["payment"]["receive_amount"])
        self.assertEqual(500000, result["payment"]["outstanding_balance"])
        self.assertEqual(1000000, result["summary"]["voucher_total"])
        self.assertEqual(500000, result["summary"]["total_received"])
        self.assertEqual(500000, result["summary"]["outstanding_balance"])
        sql_text = "\n".join(captured["sql"])
        self.assertIn("INSERT INTO", sql_text)
        self.assertIn("Payment_Receive", sql_text)
        self.assertIn("UPDATE", sql_text)
        self.assertIn('"Total_Received" = %(total_received)s', sql_text)
        self.assertIn('"Outstanding_Balance" = %(outstanding_balance)s', sql_text)
        self.assertNotIn('"Paid" =', sql_text)
        self.assertNotIn('"Amount_Received" =', sql_text)
        self.assertNotIn('"Total_Due" =', sql_text)
        self.assertNotIn('"Total_Amount" =', sql_text)

    def test_payment_receive_summary_answer_shows_kpis(self):
        answer = business_agent._fast_answer({
            "formula": "payment_receive_summary",
            "period": "all_time",
            "sector": None,
            "total_invoice_amount": 1000000,
            "total_received": 300000,
            "outstanding_receivables": 700000,
            "collection_rate_percent": 30.0,
            "aging": {"0-30": 500000, "31-60": 200000, "61-90": 0, "90+": 0},
            "sector_totals": [
                {"sector": "Farm", "invoice_amount": 1000000, "received_amount": 300000, "outstanding_balance": 700000},
            ],
            "customer_balances": [
                {"customer": "Aye Aye", "outstanding_balance": 700000},
            ],
        })

        self.assertIn("Outstanding receivables: 700,000", answer)
        self.assertIn("Collection rate: 30.0%", answer)
        self.assertIn("Aye Aye: 700,000", answer)

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

    def test_comparison_analytics_identifies_category_drivers(self):
        previous_kpi = {
            "total_income": 2_000,
            "total_expense": 1_000,
            "net_profit": 1_000,
            "profit_margin_percent": 50,
        }
        current_kpi = {
            "total_income": 2_100,
            "total_expense": 1_600,
            "net_profit": 500,
            "profit_margin_percent": 23.81,
        }
        previous_summary = {
            "total_expense": 1_000,
            "categories": [
                {"sector": "Farm", "category": "Fuel", "expense": 400},
                {"sector": "Farm", "category": "Repairs", "expense": 100},
            ],
        }
        current_summary = {
            "total_expense": 1_600,
            "categories": [
                {"sector": "Farm", "category": "Fuel", "expense": 900},
                {"sector": "Farm", "category": "Seed", "expense": 200},
            ],
        }

        analytics = business_agent._comparison_analytics(
            previous_kpi,
            current_kpi,
            previous_summary,
            current_summary,
        )

        self.assertEqual("Fuel", analytics["top_5_increases"][0]["category"])
        self.assertEqual("Repairs", analytics["top_5_decreases"][0]["category"])
        self.assertEqual("Fuel", analytics["largest_expense_categories"][0]["category"])
        self.assertEqual("Fuel", analytics["categories_over_20_percent_change"][0]["category"])
        self.assertEqual("Repairs", analytics["zero_current_value_with_previous_spending"][0]["category"])
        self.assertEqual("Seed", analytics["new_current_spending_categories"][0]["category"])
        self.assertEqual(600, analytics["kpi_summary_statistics"]["expense_change"])

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

    def test_farm_sales_customer_filter_is_detected(self):
        filters = formula_engine.extract_dimension_filters("sale income from Makro this year")

        self.assertEqual("makro", filters["farm_customer"])

    def test_farm_income_summary_does_not_treat_summary_as_customer(self):
        filters = formula_engine.extract_dimension_filters("farm income summary")

        self.assertEqual("Farm", filters["sector"])
        self.assertEqual("Income", filters["income_expense"])
        self.assertNotIn("farm_customer", filters)
        self.assertEqual("category_summary", business_agent.choose_formula("farm income summary"))

    def test_farm_section_total_income_does_not_treat_section_as_customer(self):
        filters = formula_engine.extract_dimension_filters("farm section total income")

        self.assertEqual("Farm", filters["sector"])
        self.assertEqual("Income", filters["income_expense"])
        self.assertNotIn("farm_customer", filters)
        self.assertEqual("sales_total", business_agent.choose_formula("farm section total income"))

    def test_bare_farm_customer_routes_to_sales_total(self):
        original_fetch_all = formula_engine._fetch_all

        def fake_fetch_all(sql, params=None):
            if "farm_transection" in sql:
                return [{"customer": "Makro"}]
            return []

        formula_engine._fetch_all = fake_fetch_all
        try:
            self.assertEqual("sales_total", business_agent.choose_formula("Makro"))
            self.assertEqual("makro", formula_engine.extract_dimension_filters("show Makro")["farm_customer"])
        finally:
            formula_engine._fetch_all = original_fetch_all

    def test_sales_total_includes_farm_transection_sales(self):
        original_fetch_one = formula_engine._fetch_one
        seen = []

        def fake_fetch_one(sql, params=None):
            seen.append((sql, params or {}))
            if "farm_transection" in sql:
                self.assertEqual("makro", params["farm_customer"])
                return {
                    "invoice_count": 1,
                    "total_amount": 1500000,
                    "amount_received": 500000,
                    "outstanding_amount": 1000000,
                }
            return {"total_sales": 0}

        formula_engine._fetch_one = fake_fetch_one
        try:
            result = formula_engine.sales_total("this_year", {"farm_customer": "makro"})
        finally:
            formula_engine._fetch_one = original_fetch_one

        self.assertEqual(1500000, result["total_sales"])
        self.assertEqual(500000, result["amount_received"])
        self.assertEqual(1000000, result["outstanding_amount"])
        self.assertEqual(0, result["sources"]["transection_income"])
        self.assertEqual(1500000, result["sources"]["farm_transection_total_due"])
        self.assertEqual(1, len(seen))

    def test_sales_total_combines_sotephwar_and_farm_income_tables(self):
        original_fetch_one = formula_engine._fetch_one
        original_fetch_all = formula_engine._fetch_all

        def fake_fetch_one(sql, params=None):
            if "Sotephwar_Transection" in sql:
                return {
                    "invoice_count": 2,
                    "total_amount": 1000,
                    "amount_received": 700,
                    "outstanding_amount": 300,
                }
            if "farm_transection" in sql:
                return {
                    "invoice_count": 3,
                    "total_amount": 2000,
                    "amount_received": 1500,
                    "outstanding_amount": 500,
                }
            return {"total_sales": 100}

        def fake_fetch_all(sql, params=None):
            if "Transection" in sql and "Income_Expense" in sql:
                return [
                    {
                        "Date": "2026-06-10",
                        "item": "Old item resell",
                        "amount": 100,
                        "payment_method": "Cash",
                    },
                ]
            return []

        formula_engine._fetch_one = fake_fetch_one
        formula_engine._fetch_all = fake_fetch_all
        try:
            result = formula_engine.sales_total("this_year", {"income_expense": "Income"})
        finally:
            formula_engine._fetch_one = original_fetch_one
            formula_engine._fetch_all = original_fetch_all

        self.assertEqual(3100, result["total_sales"])
        self.assertEqual(2300, result["amount_received"])
        self.assertEqual(800, result["outstanding_amount"])
        self.assertEqual(1000, result["sources"]["sotephwar_transection_total_amount"])
        self.assertEqual(2000, result["sources"]["farm_transection_total_due"])
        self.assertTrue(result["transection_income_rows"])
        self.assertEqual("Old item resell", result["transection_income_rows"][0]["item"])

    def test_farm_sales_total_excludes_sotephwar_income_table(self):
        original_fetch_one = formula_engine._fetch_one
        original_fetch_all = formula_engine._fetch_all
        seen_sql = []

        def fake_fetch_one(sql, params=None):
            seen_sql.append(sql)
            if "Sotephwar_Transection" in sql:
                return {
                    "invoice_count": 9,
                    "total_amount": 9999,
                    "amount_received": 9999,
                    "outstanding_amount": 0,
                }
            if "farm_transection" in sql:
                return {
                    "invoice_count": 2,
                    "total_amount": 4200,
                    "amount_received": 3500,
                    "outstanding_amount": 700,
                }
            return {"total_sales": 100}

        def fake_fetch_all(sql, params=None):
            seen_sql.append(sql)
            return []

        formula_engine._fetch_one = fake_fetch_one
        formula_engine._fetch_all = fake_fetch_all
        try:
            result = formula_engine.sales_total("this_year", {"sector": "Farm", "income_expense": "Income"})
        finally:
            formula_engine._fetch_one = original_fetch_one
            formula_engine._fetch_all = original_fetch_all

        self.assertEqual(4300, result["total_sales"])
        self.assertEqual(3600, result["amount_received"])
        self.assertEqual(700, result["outstanding_amount"])
        self.assertEqual(0, result["sources"]["sotephwar_transection_total_amount"])
        self.assertFalse(any("Sotephwar_Transection" in sql for sql in seen_sql))

    def test_farm_total_income_routes_to_sales_total(self):
        from tools import bi_executor
        from tools.bi_intents import BIIntent

        original_sales_total = bi_executor.sales_total
        seen = {}

        def fake_sales_total(period, filters=None):
            seen["period"] = period
            seen["filters"] = filters or {}
            return {
                "formula": "sales_total",
                "period": period,
                "total_sales": 4200,
                "amount_received": 3500,
                "outstanding_amount": 700,
            }

        bi_executor.sales_total = fake_sales_total
        try:
            payload = bi_executor.execute_intent(BIIntent(
                business="farm",
                module="income",
                report="total_income",
                period={"type": "relative", "value": "this_year"},
                output="text",
            ))
        finally:
            bi_executor.sales_total = original_sales_total

        self.assertEqual("sales_total", payload["result"]["formula"])
        self.assertEqual("Farm", seen["filters"]["sector"])
        self.assertEqual("Income", seen["filters"]["income_expense"])

    def test_top_income_ranks_by_customer_invoice_totals(self):
        original_fetch_all = formula_engine._fetch_all

        def fake_fetch_all(sql, params=None):
            if "Sotephwar_Transection" in sql:
                return [
                    {
                        "sector": "Sote Phwar",
                        "category": "Sote Phwar Sales",
                        "item": "Pwint",
                        "amount": 2000,
                        "total_amount": 2000,
                        "amount_received": 1500,
                        "outstanding_amount": 500,
                        "invoice_count": 2,
                        "payment_method": "Sotephwar_Transection",
                    },
                ]
            if "farm_transection" in sql:
                return [
                    {
                        "sector": "Farm",
                        "category": "Farm Sales",
                        "item": "Makro",
                        "amount": 3000,
                        "total_amount": 3000,
                        "amount_received": 2500,
                        "outstanding_amount": 500,
                        "invoice_count": 3,
                        "payment_method": "Farm_Transection",
                    },
                ]
            return []

        formula_engine._fetch_all = fake_fetch_all
        try:
            result = formula_engine.top_income("this_year", {"income_expense": "Income"}, limit=5)
        finally:
            formula_engine._fetch_all = original_fetch_all

        self.assertEqual("Makro", result["income"][0]["item"])
        self.assertEqual(3000, result["income"][0]["total_amount"])
        self.assertEqual(3, result["income"][0]["invoice_count"])
        self.assertEqual("Pwint", result["income"][1]["item"])

    def test_farm_income_summary_lists_farm_customers(self):
        original_fetch_all = formula_engine._fetch_all

        def fake_fetch_all(sql, params=None):
            if "farm_transection" in sql:
                return [
                    {
                        "sector": "Farm",
                        "category": "Farm Sales",
                        "item": "Makro",
                        "amount": 3000,
                        "total_amount": 3000,
                        "amount_received": 2500,
                        "outstanding_amount": 500,
                        "invoice_count": 3,
                        "payment_method": "Farm_Transection",
                    },
                ]
            return []

        formula_engine._fetch_all = fake_fetch_all
        try:
            result = formula_engine.category_summary("this_year", {"sector": "Farm", "income_expense": "Income"})
        finally:
            formula_engine._fetch_all = original_fetch_all

        self.assertEqual("Makro", result["categories"][0]["category"])
        self.assertEqual("Makro", result["categories"][0]["customer_name"])
        self.assertEqual(3000, result["categories"][0]["income"])
        self.assertEqual(2500, result["categories"][0]["amount_received"])

    def test_farm_income_summary_answer_uses_customer_name_as_revenue_customer(self):
        answer = business_agent._fast_answer({
            "formula": "category_summary",
            "period": "this_year",
            "filters": {"sector": "Farm", "income_expense": "Income"},
            "total_income": 3000,
            "categories": [
                {
                    "sector": "Farm",
                    "category": "Makro",
                    "customer_name": "Makro",
                    "income": 3000,
                    "expense": 0,
                    "net": 3000,
                    "transaction_count": 3,
                    "amount_received": 2500,
                    "outstanding_amount": 500,
                },
            ],
        })

        self.assertIn("Top Customers by Revenue", answer)
        self.assertIn("1. Makro | Total Sales: 3,000", answer)

    def test_farm_income_summary_answer_uses_customer_revenue_style(self):
        answer = business_agent._fast_answer({
            "formula": "category_summary",
            "period": "this_year",
            "filters": {"sector": "Farm", "income_expense": "Income"},
            "total_income": 4200,
            "total_expense": 0,
            "net_total": 4200,
            "transaction_count": 6,
            "categories": [
                {
                    "sector": "Farm",
                    "category": "Bala",
                    "customer_name": "Bala",
                    "income": 1200,
                    "expense": 0,
                    "net": 1200,
                    "transaction_count": 3,
                    "amount_received": 1000,
                    "outstanding_amount": 200,
                },
                {
                    "sector": "Farm",
                    "category": "Makro",
                    "customer_name": "Makro",
                    "income": 3000,
                    "expense": 0,
                    "net": 3000,
                    "transaction_count": 3,
                    "amount_received": 2500,
                    "outstanding_amount": 500,
                },
            ],
        })

        self.assertIn("KPI Summary", answer)
        self.assertIn("Total Sales: 4,200", answer)
        self.assertIn("Total Received: 3,500", answer)
        self.assertIn("Total Outstanding: 700", answer)
        self.assertIn("Top Customers by Revenue", answer)
        self.assertIn("Customer Collection Status", answer)
        self.assertLess(answer.find("Makro"), answer.find("Bala"))
        self.assertNotIn("Category summary", answer)

    def test_sotephwar_income_summary_includes_customers_sorted_by_sales_sql(self):
        original_fetch_one = formula_engine._fetch_one
        original_fetch_all = formula_engine._fetch_all
        captured = {}

        def fake_fetch_one(sql, params=None):
            return {
                "invoice_count": 3,
                "total_amount": 4600,
                "amount_received": 2900,
                "outstanding_amount": 1700,
            }

        def fake_fetch_all(sql, params=None):
            captured["sql"] = sql
            captured["params"] = params or {}
            return [
                {
                    "sector": "Sote Phwar",
                    "category": "Sote Phwar Sales",
                    "item": "Makro",
                    "customer_name": "Makro",
                    "amount": 3000,
                    "total_amount": 3000,
                    "amount_received": 2200,
                    "outstanding_amount": 800,
                    "invoice_count": 2,
                    "payment_method": "Sotephwar_Transection",
                },
            ]

        formula_engine._fetch_one = fake_fetch_one
        formula_engine._fetch_all = fake_fetch_all
        try:
            result = formula_engine.sotephwar_transection_summary("this_month")
        finally:
            formula_engine._fetch_one = original_fetch_one
            formula_engine._fetch_all = original_fetch_all

        self.assertEqual("Makro", result["customers"][0]["customer_name"])
        self.assertEqual(3000, result["customers"][0]["total_amount"])
        self.assertIn("GROUP BY COALESCE", captured["sql"])
        self.assertIn("SUM(s.\"Total_Amount\")", captured["sql"])
        self.assertIn("ORDER BY amount DESC", captured["sql"])
        self.assertNotIn("LIMIT %(limit)s", captured["sql"])

    def test_sotephwar_income_summary_answer_uses_customer_revenue_style(self):
        answer = business_agent._fast_answer({
            "formula": "sotephwar_transection_summary",
            "period": "this_year",
            "invoice_count": 3,
            "total_amount": 4600,
            "amount_received": 2900,
            "outstanding_amount": 1700,
            "customers": [
                {
                    "customer_name": "Bala",
                    "total_amount": 1200,
                    "amount_received": 500,
                    "outstanding_amount": 700,
                },
                {
                    "customer_name": "Makro",
                    "total_amount": 3000,
                    "amount_received": 2200,
                    "outstanding_amount": 800,
                },
            ],
        })

        self.assertIn("KPI Summary", answer)
        self.assertIn("Total Sales: 4,600", answer)
        self.assertIn("Total Received: 2,900", answer)
        self.assertIn("Top Customers by Revenue", answer)
        self.assertIn("Customer Collection Status", answer)
        self.assertLess(answer.find("Makro"), answer.find("Bala"))
        self.assertNotIn("Invoices:", answer)

    def test_bi_top_customers_uses_combined_income_ranking(self):
        from tools import bi_executor
        from tools.bi_intents import BIIntent

        original_top_income = bi_executor.top_income
        seen = {}

        def fake_top_income(period, filters=None, limit=5):
            seen["period"] = period
            seen["filters"] = filters
            seen["limit"] = limit
            return {"formula": "top_income", "period": period, "income": []}

        bi_executor.top_income = fake_top_income
        try:
            bi_executor.execute_intent(BIIntent(
                business="farm",
                module="income",
                report="top_customers",
                period={"type": "relative", "value": "this_year"},
                output="text",
            ))
        finally:
            bi_executor.top_income = original_top_income

        self.assertEqual("this_year", seen["period"])
        self.assertEqual({"sector": "Farm", "income_expense": "Income"}, seen["filters"])
        self.assertEqual(10, seen["limit"])

    def test_bi_farm_sales_by_customer_uses_farm_customer_filter(self):
        from tools import bi_executor
        from tools.bi_intents import BIIntent

        original_farm_customer = bi_executor.farm_transection_customer
        original_sotephwar_customer = bi_executor.sotephwar_transection_customer
        seen = {}

        def fake_farm_customer(period, customer=None, limit=50):
            seen["period"] = period
            seen["customer"] = customer
            seen["limit"] = limit
            return {
                "formula": "farm_transection_customer",
                "period": period,
                "customer": customer,
                "total_sales": 1500000,
                "amount_received": 500000,
                "outstanding_amount": 1000000,
                "invoices": [
                    {
                        "invoice_date": "2026-06-15",
                        "invoice_number": "12",
                        "customer_name": customer,
                        "total_amount": 1500000,
                        "amount_received": 500000,
                        "outstanding_amount": 1000000,
                    },
                ],
            }

        def fail_sotephwar_customer(*args, **kwargs):
            raise AssertionError("Farm sales by customer should not use Sotephwar_Transection")

        bi_executor.farm_transection_customer = fake_farm_customer
        bi_executor.sotephwar_transection_customer = fail_sotephwar_customer
        try:
            payload = bi_executor.execute_intent(BIIntent(
                business="farm",
                module="income",
                report="sales_by_customer",
                period={"type": "relative", "value": "this_year"},
                output="text",
                customer="Makro",
            ))
        finally:
            bi_executor.farm_transection_customer = original_farm_customer
            bi_executor.sotephwar_transection_customer = original_sotephwar_customer

        self.assertEqual("this_year", seen["period"])
        self.assertEqual("Makro", seen["customer"])
        self.assertEqual(50, seen["limit"])
        self.assertEqual(1500000, payload["result"]["total_sales"])
        self.assertEqual("12", payload["result"]["invoices"][0]["invoice_number"])

    def test_bi_income_detail_uses_selected_transection_income(self):
        from tools import bi_executor
        from tools.bi_intents import BIIntent

        original_list_transactions = bi_executor.list_transactions
        seen = {}

        def fake_list_transactions(period, filters=None, limit=20):
            seen["period"] = period
            seen["filters"] = filters
            seen["limit"] = limit
            return {"formula": "list_transactions", "period": period, "transactions": []}

        bi_executor.list_transactions = fake_list_transactions
        try:
            payload = bi_executor.execute_intent(BIIntent(
                business="farm",
                module="income",
                report="income_detail",
                period={"type": "relative", "value": "this_month"},
                output="pdf",
                category="Vegetable Sales",
            ))
        finally:
            bi_executor.list_transactions = original_list_transactions

        self.assertEqual("list_transactions", payload["result"]["formula"])
        self.assertEqual("this_month", seen["period"])
        self.assertEqual({"sector": "Farm", "income_expense": "Income", "category": "Vegetable Sales"}, seen["filters"])
        self.assertEqual(50, seen["limit"])

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

        self.assertIn('cm."category_name"', sql)
        self.assertIn('t."Categorization"', sql)
        self.assertIn('IN (%(category_0)s, %(category_1)s)', sql)
        self.assertEqual("makro expense", params["category_0"])
        self.assertEqual("farm wages and salary", params["category_1"])
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
            self.assertEqual(800, result["amount_received"])
            self.assertEqual(200, result["outstanding_amount"])
        finally:
            bi_executor.sotephwar_transection_summary = original_sotephwar_summary
            bi_executor.expense_total = original_expense_total

    def test_sotephwar_kpi_answer_shows_unpaid_amount(self):
        answer = business_agent._fast_answer({
            "formula": "kpi_overview",
            "period": "this_month",
            "total_income": 1000,
            "total_expense": 300,
            "net_profit": 700,
            "profit_margin_percent": 70,
            "amount_received": 800,
            "outstanding_amount": 200,
        })

        self.assertIn("Received: 800", answer)
        self.assertIn("Outstanding / unpaid: 200", answer)

    def test_sotephwar_income_menu_includes_unpaid_report(self):
        from tools.bi_catalog import reports_for

        reports = dict(reports_for("sote_phwar", "income"))

        self.assertEqual("Outstanding / Unpaid", reports["outstanding_balance"])

    def test_outstanding_balance_requires_customer(self):
        from tools.bi_intents import BIIntent, validate_intent

        missing = validate_intent(BIIntent(
            business="sote_phwar",
            module="income",
            report="outstanding_balance",
            period={"type": "relative", "value": "this_month"},
            output="text",
        ))

        self.assertIn("customer", missing)

    def test_bi_pdf_outstanding_balance_uses_two_hundred_voucher_limit(self):
        from tools import bi_executor
        from tools.bi_intents import BIIntent

        original_sotephwar_customer = bi_executor.sotephwar_transection_customer
        seen = {}

        def fake_sotephwar_customer(period, customer=None, limit=50, unpaid_only=False):
            seen["period"] = period
            seen["customer"] = customer
            seen["limit"] = limit
            seen["unpaid_only"] = unpaid_only
            return {
                "formula": "sotephwar_transection_customer",
                "period": period,
                "customer": customer,
                "unpaid_only": unpaid_only,
                "invoices": [],
            }

        bi_executor.sotephwar_transection_customer = fake_sotephwar_customer
        try:
            bi_executor.execute_intent(BIIntent(
                business="sote_phwar",
                module="income",
                report="outstanding_balance",
                period={"type": "relative", "value": "this_month"},
                output="pdf",
                customer="Ma Shwe War",
            ))
        finally:
            bi_executor.sotephwar_transection_customer = original_sotephwar_customer

        self.assertEqual("Ma Shwe War", seen["customer"])
        self.assertEqual(200, seen["limit"])
        self.assertTrue(seen["unpaid_only"])

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
        self.assertIn('cm."category_name"', captured["sql"])
        self.assertIn('t."Categorization"', captured["sql"])
        self.assertIn('LIKE %(transaction_category_search)s', captured["sql"])
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
        self.assertIn('cm."category_name"', captured["sql"])
        self.assertIn('t."Categorization"', captured["sql"])
        self.assertIn('LIKE %(transaction_category_search)s', captured["sql"])
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
                {"sector": "Retail Shop", "income_expense": "Income"},
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
