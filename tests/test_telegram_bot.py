import unittest

import telegram_bot
import telegram_kpi_bot


class FakeMessage:
    def __init__(self, chat_id, thread_id, text="hello"):
        self.chat_id = chat_id
        self.message_thread_id = thread_id
        self.text = text
        self.replies = []

    def reply_text(self, text):
        self.replies.append(text)


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

    def test_legacy_kpi_bot_rejects_family_thread(self):
        message = FakeMessage(-1003850232296, 4)

        self.assertFalse(telegram_kpi_bot._is_allowed_message(message))


if __name__ == "__main__":
    unittest.main()
