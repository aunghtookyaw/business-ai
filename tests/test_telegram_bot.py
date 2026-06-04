import unittest

import business_agent
import telegram_bot
import telegram_kpi_bot


class FakeMessage:
    def __init__(self, chat_id, thread_id, text="hello"):
        self.chat_id = chat_id
        self.message_thread_id = thread_id
        self.text = text
        self.replies = []

    def reply_text(self, text, **kwargs):
        self.replies.append({
            "text": text,
            "kwargs": kwargs,
        })


class FakeUpdate:
    def __init__(self, message):
        self.message = message


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

    def test_whereami_does_not_reply_outside_finance_thread(self):
        message = FakeMessage(-1003850232296, 4)

        telegram_bot.whereami(FakeUpdate(message), None)

        self.assertEqual([], message.replies)

    def test_menu_shows_finance_prompt_keyboard(self):
        message = FakeMessage(-1003850232296, 5)

        telegram_bot.menu(FakeUpdate(message), None)

        self.assertEqual("Tap a finance question:", message.replies[0]["text"])
        self.assertIn("reply_markup", message.replies[0]["kwargs"])
        self.assertEqual("Prompt keyboard opened.", message.replies[1]["text"])
        self.assertIn("reply_markup", message.replies[1]["kwargs"])

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
            telegram_bot.FINANCIAL_OBLIGATION_TEMPLATE,
            telegram_bot._normalize_command("Add obligation template"),
        )
        self.assertEqual(
            "__sync_obligation_calendar__",
            telegram_bot._normalize_command("Sync obligation calendar"),
        )

    def test_obligation_inline_prompt_callback_maps_to_question(self):
        self.assertEqual(
            "financial obligations due soon",
            telegram_bot._callback_question("finance:obl_due"),
        )
        self.assertEqual(
            "__sync_obligation_calendar__",
            telegram_bot._callback_question("finance:obl_calendar"),
        )

    def test_legacy_kpi_bot_rejects_family_thread(self):
        message = FakeMessage(-1003850232296, 4)

        self.assertFalse(telegram_kpi_bot._is_allowed_message(message))


if __name__ == "__main__":
    unittest.main()
