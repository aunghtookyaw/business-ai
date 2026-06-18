import unittest

import business_agent
import telegram_bot
import telegram_kpi_bot
from tools.bi_catalog import BUSINESS_MENU, reports_for


class FakeMessage:
    def __init__(self, chat_id, thread_id, text="hello"):
        self.chat_id = chat_id
        self.message_thread_id = thread_id
        self.text = text
        self.message_id = 123
        self.replies = []

    def reply_text(self, text, **kwargs):
        self.replies.append({
            "type": "text",
            "text": text,
            "kwargs": kwargs,
        })

    def reply_document(self, document, **kwargs):
        content = document.read()
        self.replies.append({
            "type": "document",
            "content": content,
            "kwargs": kwargs,
        })


class FakeUpdate:
    def __init__(self, message=None, callback_query=None):
        self.message = message
        self.callback_query = callback_query


class FakeCallbackQuery:
    def __init__(self, message, data):
        self.message = message
        self.data = data
        self.answers = []

    def answer(self, text=None):
        self.answers.append(text)


class FakeJobQueue:
    def __init__(self):
        self.jobs = []

    def run_once(self, callback, delay, context=None):
        self.jobs.append({
            "callback": callback,
            "delay": delay,
            "context": context,
        })


class FakeContext:
    def __init__(self):
        self.job_queue = FakeJobQueue()
        self.user_data = {}


class FinanceBotFilterTest(unittest.TestCase):
    def setUp(self):
        self.telegram_original_chat_id = telegram_bot.TELEGRAM_ALLOWED_CHAT_ID
        self.telegram_original_thread_id = telegram_bot.TELEGRAM_ALLOWED_THREAD_ID
        self.kpi_original_chat_id = telegram_kpi_bot.TELEGRAM_ALLOWED_CHAT_ID
        self.kpi_original_thread_id = telegram_kpi_bot.TELEGRAM_ALLOWED_THREAD_ID

        telegram_bot.TELEGRAM_ALLOWED_CHAT_ID = "-1003850232296"
        telegram_bot.TELEGRAM_ALLOWED_THREAD_ID = "5"
        telegram_kpi_bot.TELEGRAM_ALLOWED_CHAT_ID = "-1003850232296"
        telegram_kpi_bot.TELEGRAM_ALLOWED_THREAD_ID = "5"

    def tearDown(self):
        telegram_bot.TELEGRAM_ALLOWED_CHAT_ID = self.telegram_original_chat_id
        telegram_bot.TELEGRAM_ALLOWED_THREAD_ID = self.telegram_original_thread_id
        telegram_kpi_bot.TELEGRAM_ALLOWED_CHAT_ID = self.kpi_original_chat_id
        telegram_kpi_bot.TELEGRAM_ALLOWED_THREAD_ID = self.kpi_original_thread_id

    def test_finance_bot_allows_finance_thread(self):
        message = FakeMessage(-1003850232296, 5)

        self.assertTrue(telegram_bot._is_allowed_message(message))

    def test_finance_bot_rejects_family_thread(self):
        message = FakeMessage(-1003850232296, 4)

        self.assertFalse(telegram_bot._is_allowed_message(message))

    def test_finance_bot_schedules_auto_delete_for_ai_topic_message(self):
        message = FakeMessage(-1003850232296, 5)
        context = FakeContext()

        telegram_bot._schedule_auto_delete(context, message)

        self.assertEqual(1, len(context.job_queue.jobs))
        self.assertEqual(telegram_bot.AUTO_DELETE_SECONDS, context.job_queue.jobs[0]["delay"])
        self.assertEqual(
            {"chat_id": -1003850232296, "message_id": 123},
            context.job_queue.jobs[0]["context"],
        )

    def test_whereami_does_not_reply_outside_finance_thread(self):
        message = FakeMessage(-1003850232296, 4)

        telegram_bot.whereami(FakeUpdate(message), None)

        self.assertEqual([], message.replies)

    def test_menu_shows_business_intelligence_wizard(self):
        message = FakeMessage(-1003850232296, 5)
        context = FakeContext()

        telegram_bot.menu(FakeUpdate(message), context)

        self.assertEqual(2, len(message.replies))
        self.assertEqual("Prompt keyboard removed.", message.replies[0]["text"])
        self.assertIn("reply_markup", message.replies[0]["kwargs"])
        self.assertEqual("Business Intelligence", message.replies[1]["text"])
        self.assertIn("reply_markup", message.replies[1]["kwargs"])

    def test_prompts_shows_prebuilt_prompt_enquiry_with_overall_kpi_first(self):
        message = FakeMessage(-1003850232296, 5)
        context = FakeContext()

        telegram_bot.prompts(FakeUpdate(message), context)

        self.assertEqual("Prebuilt Prompt Enquiry", message.replies[0]["text"])
        markup = message.replies[0]["kwargs"]["reply_markup"]
        first_button = markup.inline_keyboard[0][0]
        self.assertEqual("Overall KPI", first_button.text)
        self.assertEqual("finance:overall_kpi", first_button.callback_data)

    def test_financial_obligation_is_available_in_bi_wizard(self):
        self.assertIn(("financial_obligation", "Financial Obligation"), BUSINESS_MENU)
        self.assertEqual(
            [
                ("financial_obligation_summary", "Obligation Summary"),
                ("financial_obligation_due", "Due Soon"),
                ("financial_obligation_list", "Obligation List"),
            ],
            reports_for("financial_obligation", "financial_obligation"),
        )

    def test_bi_wizard_builds_structured_intent_for_text_report(self):
        original_execute_intent = telegram_bot.execute_intent
        message = FakeMessage(-1003850232296, 5)
        context = FakeContext()
        seen = []

        def fake_execute_intent(intent):
            seen.append(intent.to_dict())
            return {
                "intent": intent.to_dict(),
                "title": "Sote Phwar - Expense - Total Expense",
                "period_label": "Last Month",
                "result": {
                    "formula": "expense_total",
                    "period": "last_month",
                    "total_expense": 123,
                },
            }

        telegram_bot.execute_intent = fake_execute_intent
        try:
            for data in (
                "bi:business:sote_phwar",
                "bi:module:expense",
                "bi:report:total_expense",
                "bi:period:last_month",
                "bi:output:text",
            ):
                telegram_bot.handle_bi_callback(
                    FakeUpdate(callback_query=FakeCallbackQuery(message, data)),
                    context,
                )

            self.assertEqual(
                {
                    "business": "sote_phwar",
                    "module": "expense",
                    "report": "total_expense",
                    "period": {"type": "relative", "value": "last_month"},
                    "output": "text",
                },
                seen[0],
            )
            self.assertIn("Total expense: 123", message.replies[-1]["text"])
        finally:
            telegram_bot.execute_intent = original_execute_intent

    def test_bi_wizard_builds_financial_obligation_intent(self):
        original_execute_intent = telegram_bot.execute_intent
        message = FakeMessage(-1003850232296, 5)
        context = FakeContext()
        seen = []

        def fake_execute_intent(intent):
            seen.append(intent.to_dict())
            return {
                "intent": intent.to_dict(),
                "title": "Financial Obligation - Financial Obligation - Obligation Summary",
                "period_label": "This Month",
                "result": {
                    "formula": "financial_obligation_summary",
                    "summary": [
                        {
                            "category": "Loan",
                            "status": "Active",
                            "amount": 100,
                            "obligation_count": 1,
                            "next_due_date": "2026-06-30",
                        },
                    ],
                },
            }

        telegram_bot.execute_intent = fake_execute_intent
        try:
            for data in (
                "bi:business:financial_obligation",
                "bi:module:financial_obligation",
                "bi:report:financial_obligation_summary",
                "bi:period:this_month",
                "bi:output:text",
            ):
                telegram_bot.handle_bi_callback(
                    FakeUpdate(callback_query=FakeCallbackQuery(message, data)),
                    context,
                )

            self.assertEqual(
                {
                    "business": "financial_obligation",
                    "module": "financial_obligation",
                    "report": "financial_obligation_summary",
                    "period": {"type": "relative", "value": "this_month"},
                    "output": "text",
                },
                seen[0],
            )
            self.assertIn("Financial Obligation", message.replies[-1]["text"])
        finally:
            telegram_bot.execute_intent = original_execute_intent

    def test_customer_history_uses_free_text_search_before_period(self):
        original_search_customers = telegram_bot.search_customers
        telegram_bot.search_customers = lambda text: [
            {"value": "Pwint Aung Kyaw POL", "score": 0.95},
            {"value": "Pwint Trading", "score": 0.9},
        ]
        try:
            message = FakeMessage(-1003850232296, 5)
            context = FakeContext()
            for data in (
                "bi:business:customers",
                "bi:module:customers",
                "bi:report:customer_history",
            ):
                telegram_bot.handle_bi_callback(
                    FakeUpdate(callback_query=FakeCallbackQuery(message, data)),
                    context,
                )

            search_message = FakeMessage(-1003850232296, 5, "Pwint")
            telegram_bot.handle_message(FakeUpdate(search_message), context)

            self.assertEqual(["Pwint Aung Kyaw POL", "Pwint Trading"], context.user_data[telegram_bot.BI_STATE_KEY]["candidates"])
            self.assertEqual("Select customer:", search_message.replies[-1]["text"])
        finally:
            telegram_bot.search_customers = original_search_customers

    def test_sales_by_customer_uses_free_text_search_before_period(self):
        original_search_customers = telegram_bot.search_customers
        telegram_bot.search_customers = lambda text: [
            {"value": "Pwint Aung Kyaw POL", "score": 0.95},
        ]
        try:
            message = FakeMessage(-1003850232296, 5)
            context = FakeContext()
            for data in (
                "bi:business:sote_phwar",
                "bi:module:income",
                "bi:report:sales_by_customer",
            ):
                telegram_bot.handle_bi_callback(
                    FakeUpdate(callback_query=FakeCallbackQuery(message, data)),
                    context,
                )

            self.assertEqual("customer", context.user_data[telegram_bot.BI_STATE_KEY]["awaiting"])

            search_message = FakeMessage(-1003850232296, 5, "Pwint")
            telegram_bot.handle_message(FakeUpdate(search_message), context)

            self.assertEqual(["Pwint Aung Kyaw POL"], context.user_data[telegram_bot.BI_STATE_KEY]["candidates"])
            self.assertEqual("Select customer:", search_message.replies[-1]["text"])
        finally:
            telegram_bot.search_customers = original_search_customers

    def test_outstanding_balance_uses_customer_search_before_period(self):
        original_search_customers = telegram_bot.search_customers
        telegram_bot.search_customers = lambda text: [
            {"value": "Ma Shwe War", "score": 1.0},
        ]
        try:
            message = FakeMessage(-1003850232296, 5)
            context = FakeContext()
            for data in (
                "bi:business:sote_phwar",
                "bi:module:income",
                "bi:report:outstanding_balance",
            ):
                telegram_bot.handle_bi_callback(
                    FakeUpdate(callback_query=FakeCallbackQuery(message, data)),
                    context,
                )

            self.assertEqual("customer", context.user_data[telegram_bot.BI_STATE_KEY]["awaiting"])

            search_message = FakeMessage(-1003850232296, 5, "Ma Shwe War")
            telegram_bot.handle_message(FakeUpdate(search_message), context)

            self.assertEqual(["Ma Shwe War"], context.user_data[telegram_bot.BI_STATE_KEY]["candidates"])
            self.assertEqual("Select customer:", search_message.replies[-1]["text"])
        finally:
            telegram_bot.search_customers = original_search_customers

    def test_expense_detail_uses_category_search_before_period(self):
        original_search_categories = telegram_bot.search_categories
        telegram_bot.search_categories = lambda text, **kwargs: [
            {"value": "Motor", "score": 1.0},
        ]
        try:
            message = FakeMessage(-1003850232296, 5)
            context = FakeContext()
            for data in (
                "bi:business:farm",
                "bi:module:expense",
                "bi:report:expense_detail",
            ):
                telegram_bot.handle_bi_callback(
                    FakeUpdate(callback_query=FakeCallbackQuery(message, data)),
                    context,
                )

            search_message = FakeMessage(-1003850232296, 5, "Motor")
            telegram_bot.handle_message(FakeUpdate(search_message), context)

            self.assertEqual(["Motor"], context.user_data[telegram_bot.BI_STATE_KEY]["candidates"])
            self.assertEqual("Select category:", search_message.replies[-1]["text"])
        finally:
            telegram_bot.search_categories = original_search_categories

    def test_income_detail_asks_income_name_before_period(self):
        original_search_categories = telegram_bot.search_categories
        seen = {}

        def fake_search_categories(text, **kwargs):
            seen["text"] = text
            seen["kwargs"] = kwargs
            return [{"value": "Vegetable Sales", "score": 1.0}]

        telegram_bot.search_categories = fake_search_categories
        try:
            message = FakeMessage(-1003850232296, 5)
            context = FakeContext()
            for data in (
                "bi:business:farm",
                "bi:module:income",
                "bi:report:income_detail",
            ):
                telegram_bot.handle_bi_callback(
                    FakeUpdate(callback_query=FakeCallbackQuery(message, data)),
                    context,
                )

            self.assertEqual("category", context.user_data[telegram_bot.BI_STATE_KEY]["awaiting"])
            self.assertIn("Type income name to search", message.replies[-1]["text"])

            search_message = FakeMessage(-1003850232296, 5, "Vegetable")
            telegram_bot.handle_message(FakeUpdate(search_message), context)

            self.assertEqual("Vegetable", seen["text"])
            self.assertEqual("Farm", seen["kwargs"]["sector"])
            self.assertEqual("Income", seen["kwargs"]["income_expense"])
            self.assertEqual(["Vegetable Sales"], context.user_data[telegram_bot.BI_STATE_KEY]["candidates"])
            self.assertEqual("Select income name:", search_message.replies[-1]["text"])
        finally:
            telegram_bot.search_categories = original_search_categories

    def test_income_reports_include_by_category_and_detail(self):
        reports = dict(reports_for("farm", "income"))

        self.assertEqual("Income by Category", reports["income_by_category"])
        self.assertEqual("Income Detail", reports["income_detail"])

    def test_expense_by_category_uses_typed_category_search(self):
        original_search_categories = telegram_bot.search_categories
        original_execute_intent = telegram_bot.execute_intent
        seen = []

        telegram_bot.search_categories = lambda text, **kwargs: [
            {"value": "Farm/Wages and salary", "score": 1.0},
        ]

        def fake_execute_intent(intent):
            seen.append(intent.to_dict())
            return {
                "intent": intent.to_dict(),
                "title": "Farm - Expense - Expense By Category - Farm/Wages and salary",
                "period_label": "This Month",
                "result": {
                    "formula": "category_summary",
                    "categories": [],
                },
            }

        telegram_bot.execute_intent = fake_execute_intent
        try:
            message = FakeMessage(-1003850232296, 5)
            context = FakeContext()
            for data in (
                "bi:business:farm",
                "bi:module:expense",
                "bi:report:expense_by_category",
            ):
                telegram_bot.handle_bi_callback(
                    FakeUpdate(callback_query=FakeCallbackQuery(message, data)),
                    context,
                )

            self.assertEqual("category", context.user_data[telegram_bot.BI_STATE_KEY]["awaiting"])

            telegram_bot.handle_message(FakeUpdate(FakeMessage(-1003850232296, 5, "salary")), context)
            telegram_bot.handle_bi_callback(
                FakeUpdate(callback_query=FakeCallbackQuery(message, "bi:select_category:0")),
                context,
            )
            telegram_bot.handle_bi_callback(
                FakeUpdate(callback_query=FakeCallbackQuery(message, "bi:category_done")),
                context,
            )
            for data in ("bi:period:this_month", "bi:output:text"):
                telegram_bot.handle_bi_callback(
                    FakeUpdate(callback_query=FakeCallbackQuery(message, data)),
                    context,
                )

            self.assertEqual("expense_by_category", seen[0]["report"])
            self.assertEqual(["Farm/Wages and salary"], seen[0]["categories"])
        finally:
            telegram_bot.search_categories = original_search_categories
            telegram_bot.execute_intent = original_execute_intent

    def test_voucher_pdf_uses_chart_card_export(self):
        original_execute_intent = telegram_bot.execute_intent
        original_chart_pdf = telegram_bot.create_chart_pdf_report_from_result
        original_write_pdf = telegram_bot._write_pdf_export
        captured = {}

        def fake_execute_intent(intent):
            return {
                "intent": intent.to_dict(),
                "title": "Sote Phwar - Income - Sales By Customer",
                "period_label": "This Month",
                "result": {
                    "formula": "sotephwar_transection_customer",
                    "invoices": [
                        {
                            "invoice_number": "12",
                            "invoice_date": "2026-06-01",
                            "customer_name": "Very Long Customer Name That Must Not Shift Columns",
                            "total_amount": 1000000,
                            "amount_received": 250000,
                            "outstanding_amount": 750000,
                        },
                    ],
                },
            }

        def fake_chart_pdf(result, question, output_path, title=telegram_bot.PDF_EXPORT_TITLE, spec=None):
            captured["formula"] = result["formula"]
            captured["question"] = question
            with open(output_path, "wb") as pdf_file:
                pdf_file.write(b"%PDF-1.4\nvoucher cards\n%%EOF\n")
            return True

        def fake_write_pdf(text, output_path, title=telegram_bot.PDF_EXPORT_TITLE):
            raise AssertionError("Voucher PDFs should use chart card export")

        telegram_bot.execute_intent = fake_execute_intent
        telegram_bot.create_chart_pdf_report_from_result = fake_chart_pdf
        telegram_bot._write_pdf_export = fake_write_pdf
        try:
            message = FakeMessage(-1003850232296, 5)
            context = FakeContext()
            context.user_data[telegram_bot.BI_STATE_KEY] = {
                "business": "sote_phwar",
                "module": "income",
                "report": "sales_by_customer",
                "period": {"type": "relative", "value": "this_month"},
                "output": "pdf",
                "customer": "Very Long Customer",
            }

            telegram_bot._execute_bi_output(message, context)
        finally:
            telegram_bot.execute_intent = original_execute_intent
            telegram_bot.create_chart_pdf_report_from_result = original_chart_pdf
            telegram_bot._write_pdf_export = original_write_pdf

        self.assertEqual("document", message.replies[-1]["type"])
        self.assertEqual("sotephwar_transection_customer", captured["formula"])
        self.assertEqual("Sote Phwar - Income - Sales By Customer", captured["question"])

    def test_income_detail_pdf_uses_transaction_ledger_export(self):
        original_execute_intent = telegram_bot.execute_intent
        original_chart_pdf = telegram_bot.create_chart_pdf_report_from_result
        original_write_pdf = telegram_bot._write_pdf_export
        captured = {}

        def fake_execute_intent(intent):
            return {
                "intent": intent.to_dict(),
                "title": "Farm - Income - Income Detail",
                "period_label": "This Month",
                "result": {
                    "formula": "list_transactions",
                    "transactions": [
                        {
                            "Date": "2026-06-01",
                            "sector": "Farm",
                            "category": "Vegetable Sales",
                            "item": "General income filling",
                            "amount": 500000,
                            "payment_method": "K Pay",
                        },
                    ],
                },
            }

        def fake_chart_pdf(result, question, output_path, title=telegram_bot.PDF_EXPORT_TITLE):
            captured["formula"] = result["formula"]
            captured["question"] = question
            captured["title"] = title
            with open(output_path, "wb") as pdf_file:
                pdf_file.write(b"%PDF-1.4\nincome detail ledger\n%%EOF\n")
            return True

        def fail_write_pdf(*args, **kwargs):
            raise AssertionError("Income Detail PDFs should use chart_pdf ledger export")

        telegram_bot.execute_intent = fake_execute_intent
        telegram_bot.create_chart_pdf_report_from_result = fake_chart_pdf
        telegram_bot._write_pdf_export = fail_write_pdf
        try:
            message = FakeMessage(-1003850232296, 5)
            context = FakeContext()
            context.user_data[telegram_bot.BI_STATE_KEY] = {
                "business": "farm",
                "module": "income",
                "report": "income_detail",
                "period": {"type": "relative", "value": "this_month"},
                "output": "pdf",
                "category": "Vegetable Sales",
            }

            telegram_bot._execute_bi_output(message, context)
        finally:
            telegram_bot.execute_intent = original_execute_intent
            telegram_bot.create_chart_pdf_report_from_result = original_chart_pdf
            telegram_bot._write_pdf_export = original_write_pdf

        self.assertEqual("document", message.replies[-1]["type"])
        self.assertEqual("list_transactions", captured["formula"])
        self.assertEqual("Farm - Income - Income Detail", captured["question"])
        self.assertEqual("Farm - Income - Income Detail", captured["title"])

    def test_sotephwar_expense_category_search_is_sector_scoped(self):
        original_search_categories = telegram_bot.search_categories
        seen = []

        def fake_search_categories(text, **kwargs):
            seen.append(kwargs)
            return [{"value": "Sote Phwar Transport", "score": 1.0}]

        telegram_bot.search_categories = fake_search_categories
        try:
            message = FakeMessage(-1003850232296, 5)
            context = FakeContext()
            for data in (
                "bi:business:sote_phwar",
                "bi:module:expense",
                "bi:report:expense_detail",
            ):
                telegram_bot.handle_bi_callback(
                    FakeUpdate(callback_query=FakeCallbackQuery(message, data)),
                    context,
                )

            telegram_bot.handle_message(FakeUpdate(FakeMessage(-1003850232296, 5, "transport")), context)

            self.assertEqual("Sote Phwar", seen[0]["sector"])
            self.assertEqual("Expense", seen[0]["income_expense"])
        finally:
            telegram_bot.search_categories = original_search_categories

    def test_expense_detail_allows_multiple_category_selection(self):
        original_search_categories = telegram_bot.search_categories
        original_execute_intent = telegram_bot.execute_intent
        searches = {
            "Makro": [{"value": "Makro Expense", "score": 1.0}],
            "Wages": [{"value": "Farm/Wages and salary", "score": 1.0}],
        }
        seen = []

        telegram_bot.search_categories = lambda text, **kwargs: searches.get(text, [])

        def fake_execute_intent(intent):
            seen.append(intent.to_dict())
            return {
                "intent": intent.to_dict(),
                "title": "Sote Phwar - Expense - Expense Detail - Makro Expense, Farm/Wages and salary",
                "period_label": "Last Month",
                "result": {
                    "formula": "list_transactions",
                    "transactions": [],
                },
            }

        telegram_bot.execute_intent = fake_execute_intent
        try:
            message = FakeMessage(-1003850232296, 5)
            context = FakeContext()
            for data in (
                "bi:business:sote_phwar",
                "bi:module:expense",
                "bi:report:expense_detail",
            ):
                telegram_bot.handle_bi_callback(
                    FakeUpdate(callback_query=FakeCallbackQuery(message, data)),
                    context,
                )

            telegram_bot.handle_message(FakeUpdate(FakeMessage(-1003850232296, 5, "Makro")), context)
            telegram_bot.handle_bi_callback(
                FakeUpdate(callback_query=FakeCallbackQuery(message, "bi:select_category:0")),
                context,
            )
            telegram_bot.handle_message(FakeUpdate(FakeMessage(-1003850232296, 5, "Wages")), context)
            telegram_bot.handle_bi_callback(
                FakeUpdate(callback_query=FakeCallbackQuery(message, "bi:select_category:0")),
                context,
            )
            telegram_bot.handle_bi_callback(
                FakeUpdate(callback_query=FakeCallbackQuery(message, "bi:category_done")),
                context,
            )
            for data in ("bi:period:last_month", "bi:output:text"):
                telegram_bot.handle_bi_callback(
                    FakeUpdate(callback_query=FakeCallbackQuery(message, data)),
                    context,
                )

            self.assertEqual(
                ["Makro Expense", "Farm/Wages and salary"],
                seen[0]["categories"],
            )
            self.assertEqual("expense_detail", seen[0]["report"])
        finally:
            telegram_bot.search_categories = original_search_categories
            telegram_bot.execute_intent = original_execute_intent

    def test_sotephwar_expense_comparison_asks_for_output_format(self):
        message = FakeMessage(-1003850232296, 5, "compare sote phwar expenses of last month and this month")
        context = FakeContext()

        telegram_bot.handle_message(FakeUpdate(message), context)

        self.assertEqual("Choose output format for Sote Phwar expense comparison:", message.replies[-1]["text"])
        self.assertEqual(
            "compare sote phwar expenses of last month and this month",
            context.user_data[telegram_bot.BI_STATE_KEY]["comparison_question"],
        )

    def test_farm_expense_comparison_asks_for_output_format(self):
        message = FakeMessage(-1003850232296, 5, "compare last month and this month farm expenses")
        context = FakeContext()

        telegram_bot.handle_message(FakeUpdate(message), context)

        self.assertEqual("Choose output format for Farm expense comparison:", message.replies[-1]["text"])
        self.assertEqual("farm", context.user_data[telegram_bot.BI_STATE_KEY]["comparison_business"])
        self.assertEqual(
            "compare last month and this month farm expenses",
            context.user_data[telegram_bot.BI_STATE_KEY]["comparison_question"],
        )

    def test_farm_expense_comparison_uses_farm_sector_data(self):
        from tools import comparison_reports

        original_category_summary = comparison_reports.category_summary
        original_ask_ai = comparison_reports.ask_ai
        seen_filters = []

        def fake_category_summary(period, filters):
            seen_filters.append(filters)
            return {
                "formula": "category_summary",
                "total_expense": 1000 if period == "last_month" else 1500,
                "transaction_count": 1,
                "categories": [
                    {
                        "category": "Farm Wages",
                        "expense": 1000 if period == "last_month" else 1500,
                        "transaction_count": 1,
                    },
                ],
            }

        comparison_reports.category_summary = fake_category_summary
        comparison_reports.ask_ai = lambda *args, **kwargs: "Business comment: Farm expense moved."
        try:
            payload = comparison_reports.expense_month_comparison(
                "compare last month and this month farm expenses",
                "farm",
            )
        finally:
            comparison_reports.category_summary = original_category_summary
            comparison_reports.ask_ai = original_ask_ai

        self.assertEqual("Farm - Expense - Month Comparison", payload["title"])
        self.assertEqual(
            [
                {"sector": "Farm", "income_expense": "Expense"},
                {"sector": "Farm", "income_expense": "Expense"},
            ],
            seen_filters,
        )
        self.assertIn("analytics", payload["result"])
        self.assertIn("raw_data", payload["result"])

    def test_expense_comparison_analytics_flags_business_signals(self):
        from tools import comparison_reports

        previous = {
            "total_expense": 1_000,
            "transaction_count": 3,
            "categories": [
                {"sector": "Farm", "category": "Fuel", "expense": 400},
                {"sector": "Farm", "category": "Wages", "expense": 500},
                {"sector": "Farm", "category": "Repairs", "expense": 100},
            ],
        }
        current = {
            "total_expense": 1_600,
            "transaction_count": 2,
            "categories": [
                {"sector": "Farm", "category": "Fuel", "expense": 900},
                {"sector": "Farm", "category": "Wages", "expense": 500},
                {"sector": "Farm", "category": "Seed", "expense": 200},
            ],
        }

        rows = comparison_reports._category_rows(previous, current)
        analytics = comparison_reports._analytics(previous, current, rows)

        self.assertEqual("Fuel", analytics["top_5_increases"][0]["category"])
        self.assertEqual(500, analytics["top_5_increases"][0]["change"])
        self.assertEqual("Repairs", analytics["top_5_decreases"][0]["category"])
        self.assertEqual("Fuel", analytics["largest_expense_categories"][0]["category"])
        self.assertEqual(56.25, analytics["largest_expense_categories"][0]["current_contribution_percent"])
        self.assertEqual("Fuel", analytics["categories_over_20_percent_change"][0]["category"])
        self.assertEqual("Repairs", analytics["zero_current_value_with_previous_spending"][0]["category"])
        self.assertEqual("Seed", analytics["new_current_spending_categories"][0]["category"])
        self.assertEqual(600, analytics["kpi_summary_statistics"]["expense_change"])

    def test_farm_expense_comparison_text_is_business_report_not_json(self):
        original_comparison = telegram_bot.expense_month_comparison
        captured = {}

        def fake_comparison(question, business):
            captured["business"] = business
            return {
                "intent": {
                    "business": business,
                    "module": "expense",
                    "report": "expense_comparison",
                },
                "title": "Farm - Expense - Month Comparison",
                "period_label": "Last Month vs This Month",
                "result": {
                    "formula": "expense_period_comparison",
                    "periods": [
                        {"label": "Last Month", "total_expense": 1000, "paid": 1000, "outstanding": 0, "transaction_count": 1},
                        {"label": "This Month", "total_expense": 1500, "paid": 1500, "outstanding": 0, "transaction_count": 2},
                    ],
                    "categories": [
                        {"category": "Packaging", "previous_amount": 1000, "current_amount": 1500, "change": 500, "change_percent": 50},
                    ],
                    "total_change": 500,
                    "total_change_percent": 50,
                    "ai_comment": "Business comment: expenses increased. Review Packaging.",
                },
            }

        telegram_bot.expense_month_comparison = fake_comparison
        try:
            message = FakeMessage(-1003850232296, 5)
            context = FakeContext()
            context.user_data[telegram_bot.BI_STATE_KEY] = {
                "comparison_question": "compare last month and this month farm expenses",
                "comparison_business": "farm",
            }

            telegram_bot.handle_bi_callback(
                FakeUpdate(callback_query=FakeCallbackQuery(message, "bi:output:text")),
                context,
            )

            text = message.replies[-1]["text"]
            self.assertIn("Expense Comparison", text)
            self.assertIn("Local AI Comment", text)
            self.assertIn("Category Comparison Table", text)
            self.assertIn("Packaging | 1,000 | 1,500 | 500 | 50%", text)
            self.assertNotIn("Structured intent", text)
            self.assertNotIn("{'business'", text)
            self.assertEqual("farm", captured["business"])
        finally:
            telegram_bot.expense_month_comparison = original_comparison

    def test_sotephwar_expense_comparison_pdf_uses_chart_export(self):
        original_comparison = telegram_bot.expense_month_comparison
        original_chart_pdf = telegram_bot.create_chart_pdf_report_from_result
        captured = {}

        def fake_comparison(question, business):
            captured["business"] = business
            return {
                "intent": {"business": business, "module": "expense", "report": "expense_comparison"},
                "title": "Sote Phwar - Expense - Month Comparison",
                "period_label": "Last Month vs This Month",
                "result": {"formula": "expense_period_comparison", "periods": [], "categories": [], "ai_comment": "comment"},
            }

        def fake_chart_pdf(result, question, output_path, title=telegram_bot.PDF_EXPORT_TITLE, spec=None):
            captured["formula"] = result["formula"]
            with open(output_path, "wb") as pdf_file:
                pdf_file.write(b"%PDF-1.4\ncomparison line chart\n%%EOF\n")
            return True

        telegram_bot.expense_month_comparison = fake_comparison
        telegram_bot.create_chart_pdf_report_from_result = fake_chart_pdf
        try:
            message = FakeMessage(-1003850232296, 5)
            context = FakeContext()
            context.user_data[telegram_bot.BI_STATE_KEY] = {
                "comparison_question": "compare sote phwar expenses of last month and this month",
                "comparison_business": "sote_phwar",
            }

            telegram_bot.handle_bi_callback(
                FakeUpdate(callback_query=FakeCallbackQuery(message, "bi:output:pdf")),
                context,
            )

            self.assertEqual("expense_period_comparison", captured["formula"])
            self.assertEqual("sote_phwar", captured["business"])
            self.assertEqual("document", message.replies[-1]["type"])
            self.assertTrue(message.replies[-1]["content"].startswith(b"%PDF"))
        finally:
            telegram_bot.expense_month_comparison = original_comparison
            telegram_bot.create_chart_pdf_report_from_result = original_chart_pdf

    def test_tapped_prompt_label_maps_to_finance_question(self):
        self.assertEqual(
            "business advice for this month",
            telegram_bot._normalize_command("Business advice"),
        )
        self.assertEqual(
            "compare month to month",
            telegram_bot._normalize_command("Compare month to month"),
        )

    def test_sotephwar_prompt_labels_map_to_table_questions(self):
        self.assertEqual(
            "show Sote Phwar vouchers by customer this month",
            telegram_bot._normalize_command("Sote Phwar vouchers"),
        )
        self.assertEqual(
            "show unpaid Sote Phwar vouchers by customer",
            telegram_bot._normalize_command("Sote Phwar unpaid"),
        )
        self.assertEqual(
            "Sotephwar inventory stock Sote Phwar 4L",
            telegram_bot._normalize_command("Sote Phwar 4L quantity"),
        )

    def test_sotephwar_prompt_questions_route_to_expected_formulas(self):
        self.assertEqual(
            "sotephwar_transection_customer",
            business_agent.choose_formula(telegram_bot._normalize_command("Sote Phwar vouchers")),
        )
        self.assertEqual(
            "sotephwar_inventory_stock",
            business_agent.choose_formula(telegram_bot._normalize_command("Sote Phwar 4L quantity")),
        )
        self.assertEqual(
            "sotephwar_transection_top",
            business_agent.choose_formula(telegram_bot._normalize_command("Sote Phwar top invoices")),
        )

    def test_inline_prompt_callback_maps_to_question(self):
        self.assertEqual(
            "top expenses",
            telegram_bot._callback_question("finance:top_expenses"),
        )
        self.assertEqual(
            "show unpaid Sote Phwar vouchers by customer",
            telegram_bot._callback_question("finance:sote_unpaid"),
        )

    def test_inventory_prompt_labels_map_to_inventory_questions(self):
        self.assertEqual(
            "Sotephwar inventory stock",
            telegram_bot._normalize_command("Sote inventory stock"),
        )
        self.assertEqual(
            "Sotephwar inventory stock heho",
            telegram_bot._normalize_command("Heho stock"),
        )
        self.assertEqual(
            "Sotephwar inventory stock Sote Phwar 100 mL",
            telegram_bot._normalize_command("Sote Phwar 100 mL quantity"),
        )

    def test_inventory_inline_prompt_callback_maps_to_question(self):
        self.assertEqual(
            "Sotephwar inventory movement this month",
            telegram_bot._callback_question("finance:inv_movement"),
        )

    def test_obligation_prompt_labels_map_to_questions(self):
        self.assertEqual(
            "financial obligations summary",
            telegram_bot._normalize_command("Obligation summary"),
        )
        self.assertEqual(
            "financial obligations due soon",
            telegram_bot._normalize_command("Obligation due soon"),
        )
        self.assertEqual(
            telegram_bot.SOTEPHWAR_PAYMENT_TEMPLATE,
            telegram_bot._normalize_command("Sote payment template"),
        )
        self.assertEqual(
            "__sync_obligation_calendar__",
            telegram_bot._normalize_command("Sync obligation calendar"),
        )

    def test_obligation_inline_prompt_callback_maps_to_question(self):
        self.assertEqual(
            "this year KPI pdf",
            telegram_bot._callback_question("finance:overall_kpi"),
        )
        self.assertEqual(
            "financial obligations due soon",
            telegram_bot._callback_question("finance:obl_due"),
        )
        self.assertEqual(
            "__sync_obligation_calendar__",
            telegram_bot._callback_question("finance:obl_calendar"),
        )
        self.assertEqual(
            telegram_bot.SOTEPHWAR_PAYMENT_TEMPLATE,
            telegram_bot._callback_question("finance:sote_payment_template"),
        )

    def test_overall_kpi_is_first_prebuilt_prompt(self):
        markup = telegram_bot._finance_inline_markup()

        first_button = markup.inline_keyboard[0][0]
        self.assertEqual("Overall KPI", first_button.text)
        self.assertEqual("finance:overall_kpi", first_button.callback_data)

    def test_send_pdf_text_maps_to_pdf_export(self):
        self.assertEqual(
            telegram_bot.PDF_EXPORT_COMMAND,
            telegram_bot._normalize_command("send pdf"),
        )
        self.assertEqual(
            f"{telegram_bot.PDF_EXPORT_COMMAND}:top expenses",
            telegram_bot._normalize_command("/send_pdf top expenses"),
        )
        self.assertEqual(
            f"{telegram_bot.PDF_EXPORT_COMMAND}:Pwint Aung Kyaw (MDY) transection",
            telegram_bot._normalize_command("Pwint Aung Kyaw (MDY) transection send pdf"),
        )
        self.assertEqual(
            "top expenses",
            telegram_bot._pdf_export_question(f"{telegram_bot.PDF_EXPORT_COMMAND}:Top expenses"),
        )
        self.assertEqual(
            telegram_bot.JPEG_EXPORT_COMMAND,
            telegram_bot._normalize_command("send jpeg"),
        )
        self.assertEqual(
            f"{telegram_bot.JPEG_EXPORT_COMMAND}:top expenses",
            telegram_bot._normalize_command("top expenses send jpg"),
        )
        self.assertEqual(
            telegram_bot.PDF_JPEG_EXPORT_COMMAND,
            telegram_bot._normalize_command("send pdf and jpeg"),
        )
        self.assertEqual(
            f"{telegram_bot.PDF_JPEG_EXPORT_COMMAND}:cash flow",
            telegram_bot._normalize_command("cash flow send pdf and jpeg"),
        )
        self.assertEqual(
            f"{telegram_bot.PDF_EXPORT_COMMAND}:CEO monthly management report pdf",
            telegram_bot._normalize_command("CEO monthly management report pdf"),
        )
        self.assertEqual(
            "CEO monthly management report pdf",
            telegram_bot._pdf_export_question(f"{telegram_bot.PDF_EXPORT_COMMAND}:CEO monthly management report pdf"),
        )
        self.assertEqual(
            f"{telegram_bot.PDF_EXPORT_COMMAND}:local AI qwen 3 finance report pdf",
            telegram_bot._normalize_command("local AI qwen 3 finance report pdf"),
        )
        self.assertEqual(
            telegram_bot.CEO_PDF_EXPORT_TITLE,
            telegram_bot._export_title_for_question("local AI qwen 3 finance report pdf"),
        )
        self.assertEqual(
            f"{telegram_bot.PDF_EXPORT_COMMAND}:this month KPI pdf",
            telegram_bot._normalize_command("this month KPI pdf"),
        )
        self.assertEqual(
            telegram_bot.CEO_PDF_EXPORT_TITLE,
            telegram_bot._export_title_for_question("this month KPI pdf"),
        )

    def test_local_ai_finance_pdf_uses_ceo_report_renderer(self):
        original_create_chart_pdf_report = telegram_bot.create_chart_pdf_report
        original_answer_question = telegram_bot.answer_question
        seen = []

        def fake_create_chart_pdf_report(question, output_path, title=telegram_bot.PDF_EXPORT_TITLE):
            seen.append({"question": question, "title": title})
            with open(output_path, "wb") as pdf_file:
                pdf_file.write(b"%PDF-1.4\nceo report\n%%EOF\n")
            return True

        def fail_answer_question(question):
            raise AssertionError("CEO PDF export should not fall back to local-AI text export")

        telegram_bot.create_chart_pdf_report = fake_create_chart_pdf_report
        telegram_bot.answer_question = fail_answer_question
        try:
            message = FakeMessage(-1003850232296, 5)

            telegram_bot._answer_finance_question(
                message,
                telegram_bot._normalize_command("local AI qwen 3 finance report pdf"),
            )

            self.assertEqual("document", message.replies[0]["type"])
            self.assertEqual("local AI qwen 3 finance report pdf", seen[0]["question"])
            self.assertEqual(telegram_bot.CEO_PDF_EXPORT_TITLE, seen[0]["title"])
            self.assertTrue(message.replies[0]["kwargs"]["filename"].startswith("bigshot_ceo_management_report_"))
        finally:
            telegram_bot.create_chart_pdf_report = original_create_chart_pdf_report
            telegram_bot.answer_question = original_answer_question

    def test_send_pdf_replies_with_document(self):
        original_answer_question = telegram_bot.answer_question
        original_create_chart_pdf_report = telegram_bot.create_chart_pdf_report
        original_write_pdf_export = telegram_bot._write_pdf_export

        def fake_answer_question(question):
            self.assertEqual("this month kpi", question)
            return "KPI overview for this month\nIncome: 100"

        def fake_create_chart_pdf_report(question, output_path, title=telegram_bot.PDF_EXPORT_TITLE):
            return False

        def fake_write_pdf_export(text, output_path, title=telegram_bot.PDF_EXPORT_TITLE):
            with open(output_path, "wb") as pdf_file:
                pdf_file.write(b"%PDF-1.4\nfake\n%%EOF\n")

        telegram_bot.answer_question = fake_answer_question
        telegram_bot.create_chart_pdf_report = fake_create_chart_pdf_report
        telegram_bot._write_pdf_export = fake_write_pdf_export
        try:
            message = FakeMessage(-1003850232296, 5)

            telegram_bot._answer_finance_question(message, telegram_bot.PDF_EXPORT_COMMAND)

            self.assertEqual("document", message.replies[0]["type"])
            self.assertTrue(message.replies[0]["content"].startswith(b"%PDF"))
            self.assertEqual(
                "PDF export: this month kpi",
                message.replies[0]["kwargs"]["caption"],
            )
            self.assertIn("reply_markup", message.replies[0]["kwargs"])
        finally:
            telegram_bot.answer_question = original_answer_question
            telegram_bot.create_chart_pdf_report = original_create_chart_pdf_report
            telegram_bot._write_pdf_export = original_write_pdf_export

    def test_send_pdf_and_jpeg_replies_with_two_documents(self):
        original_create_chart_pdf_report = telegram_bot.create_chart_pdf_report
        original_write_jpeg_export = telegram_bot._write_jpeg_export

        def fake_create_chart_pdf_report(question, output_path, title=telegram_bot.PDF_EXPORT_TITLE):
            with open(output_path, "wb") as pdf_file:
                pdf_file.write(b"%PDF-1.4\nfake\n%%EOF\n")
            return True

        def fake_write_jpeg_export(pdf_path, jpeg_path):
            with open(jpeg_path, "wb") as jpeg_file:
                jpeg_file.write(b"\xff\xd8\xfffake")

        telegram_bot.create_chart_pdf_report = fake_create_chart_pdf_report
        telegram_bot._write_jpeg_export = fake_write_jpeg_export
        try:
            message = FakeMessage(-1003850232296, 5)

            telegram_bot._answer_finance_question(message, telegram_bot.PDF_JPEG_EXPORT_COMMAND)

            self.assertEqual(2, len(message.replies))
            self.assertTrue(message.replies[0]["content"].startswith(b"%PDF"))
            self.assertTrue(message.replies[1]["content"].startswith(b"\xff\xd8\xff"))
            self.assertTrue(message.replies[0]["kwargs"]["filename"].endswith(".pdf"))
            self.assertTrue(message.replies[1]["kwargs"]["filename"].endswith(".jpg"))
        finally:
            telegram_bot.create_chart_pdf_report = original_create_chart_pdf_report
            telegram_bot._write_jpeg_export = original_write_jpeg_export

    def test_direct_finance_text_question_uses_executive_mode(self):
        original_executive_answer = telegram_bot.answer_executive_question
        telegram_bot.answer_executive_question = lambda question: f"executive answer for {question}"
        try:
            message = FakeMessage(-1003850232296, 5, "this month income")
            context = FakeContext()

            telegram_bot.handle_message(FakeUpdate(message), context)

            self.assertEqual("executive answer for this month income", message.replies[-1]["text"])
        finally:
            telegram_bot.answer_executive_question = original_executive_answer

    def test_slash_command_still_uses_structured_finance_answer(self):
        original_answer_question = telegram_bot.answer_question
        original_executive_answer = telegram_bot.answer_executive_question
        telegram_bot.answer_question = lambda question: f"structured answer for {question}"

        def fail_executive_answer(question):
            raise AssertionError("Slash commands should stay on structured finance path")

        telegram_bot.answer_executive_question = fail_executive_answer
        try:
            message = FakeMessage(-1003850232296, 5, "/month_income")
            context = FakeContext()

            telegram_bot.handle_message(FakeUpdate(message), context)

            self.assertEqual("structured answer for this month income", message.replies[-1]["text"])
        finally:
            telegram_bot.answer_question = original_answer_question
            telegram_bot.answer_executive_question = original_executive_answer

    def test_executive_pdf_request_sends_document(self):
        original_executive_answer = telegram_bot.answer_executive_question
        original_ceo_pdf = telegram_bot.create_ceo_management_pdf_report
        telegram_bot.answer_executive_question = lambda question: "BigShot Intelligence Report\n\nExecutive Summary\nRevenue is stable."
        calls = []

        def fake_ceo_pdf(question, output_path, title=""):
            calls.append({"question": question, "title": title})
            with open(output_path, "wb") as output:
                output.write(b"%PDF CEO report")
            return True

        telegram_bot.create_ceo_management_pdf_report = fake_ceo_pdf
        try:
            message = FakeMessage(-1003850232296, 5, "Analyze revenue pdf")
            context = FakeContext()

            telegram_bot.handle_message(FakeUpdate(message), context)

            self.assertEqual("document", message.replies[-1]["type"])
            self.assertTrue(message.replies[-1]["content"].startswith(b"%PDF"))
            self.assertTrue(message.replies[-1]["kwargs"]["filename"].endswith(".pdf"))
            self.assertEqual([{"question": "Analyze revenue pdf", "title": telegram_bot.CEO_PDF_EXPORT_TITLE}], calls)
        finally:
            telegram_bot.answer_executive_question = original_executive_answer
            telegram_bot.create_ceo_management_pdf_report = original_ceo_pdf

    def test_executive_pdf_request_falls_back_to_text_pdf(self):
        original_executive_answer = telegram_bot.answer_executive_question
        original_ceo_pdf = telegram_bot.create_ceo_management_pdf_report
        telegram_bot.answer_executive_question = lambda question: "BigShot Intelligence Report\n\nExecutive Summary\nRevenue is stable."
        telegram_bot.create_ceo_management_pdf_report = lambda question, output_path, title="": False
        try:
            message = FakeMessage(-1003850232296, 5, "Analyze revenue pdf")
            context = FakeContext()

            telegram_bot.handle_message(FakeUpdate(message), context)

            self.assertEqual("document", message.replies[-1]["type"])
            self.assertTrue(message.replies[-1]["content"].startswith(b"%PDF"))
        finally:
            telegram_bot.answer_executive_question = original_executive_answer
            telegram_bot.create_ceo_management_pdf_report = original_ceo_pdf

    def test_legacy_kpi_bot_rejects_family_thread(self):
        message = FakeMessage(-1003850232296, 4)

        self.assertFalse(telegram_kpi_bot._is_allowed_message(message))


if __name__ == "__main__":
    unittest.main()
