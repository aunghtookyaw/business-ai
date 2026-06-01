import unittest
from unittest.mock import patch

import family_ai_bot
from tools import web_scraper


class FakeMessage:
    def __init__(self, chat_id, thread_id):
        self.chat_id = chat_id
        self.message_thread_id = thread_id
        self.replies = []

    def reply_text(self, text):
        self.replies.append(text)


class FakeUpdate:
    def __init__(self, message):
        self.message = message


class FamilyAiBotFilterTest(unittest.TestCase):
    def setUp(self):
        self.original_chat_id = family_ai_bot.TELEGRAM_ALLOWED_CHAT_ID
        self.original_thread_id = family_ai_bot.TELEGRAM_ALLOWED_THREAD_ID
        self.original_ignored_thread_ids = family_ai_bot.TELEGRAM_IGNORED_THREAD_IDS
        family_ai_bot.TELEGRAM_ALLOWED_CHAT_ID = "-1003850232296"
        family_ai_bot.TELEGRAM_ALLOWED_THREAD_ID = "4"
        family_ai_bot.TELEGRAM_IGNORED_THREAD_IDS = "5"

    def tearDown(self):
        family_ai_bot.TELEGRAM_ALLOWED_CHAT_ID = self.original_chat_id
        family_ai_bot.TELEGRAM_ALLOWED_THREAD_ID = self.original_thread_id
        family_ai_bot.TELEGRAM_IGNORED_THREAD_IDS = self.original_ignored_thread_ids

    def test_allows_family_ai_thread(self):
        message = FakeMessage(-1003850232296, 4)

        self.assertTrue(family_ai_bot._is_allowed_message(message))

    def test_rejects_main_family_chat_when_family_ai_thread_is_required(self):
        message = FakeMessage(-1003850232296, None)

        self.assertFalse(family_ai_bot._is_allowed_message(message))

    def test_rejects_finance_thread(self):
        message = FakeMessage(-1003850232296, 5)

        self.assertFalse(family_ai_bot._is_allowed_message(message))

    def test_whereami_does_not_reply_in_ignored_finance_thread(self):
        message = FakeMessage(-1003850232296, 5)

        family_ai_bot.whereami(FakeUpdate(message), None)

        self.assertEqual([], message.replies)

    def test_ask_family_ai_uses_openclaw_client_with_family_model(self):
        with patch.object(family_ai_bot, "ask_ai", return_value="answer") as ask_ai:
            answer = family_ai_bot.ask_family_ai("hello")

        self.assertEqual("answer", answer)
        ask_ai.assert_called_once()
        self.assertIn("BigShot_Guy_Bot", ask_ai.call_args.args[0])
        self.assertEqual(family_ai_bot.AI_MODEL, ask_ai.call_args.kwargs["model"])
        self.assertEqual(120, ask_ai.call_args.kwargs["timeout"])

    def test_ask_family_ai_includes_scraped_page_content_for_urls(self):
        scrape_result = {
            "pages": [{
                "url": "https://example.com",
                "status_code": 200,
                "content_type": "text/html",
                "text": "Example page text",
                "truncated": False,
            }],
            "errors": [],
        }

        with patch.object(family_ai_bot, "scrape_urls_from_text", return_value=scrape_result):
            with patch.object(family_ai_bot, "ask_ai", return_value="answer") as ask_ai:
                answer = family_ai_bot.ask_family_ai("summarize https://example.com")

        self.assertEqual("answer", answer)
        self.assertIn("Web page content:", ask_ai.call_args.args[0])
        self.assertIn("Example page text", ask_ai.call_args.args[0])

    def test_extract_urls_strips_sentence_punctuation(self):
        self.assertEqual(
            ["https://example.com/path"],
            web_scraper.extract_urls("read https://example.com/path."),
        )

    def test_html_to_text_ignores_script_content(self):
        self.assertEqual(
            "Title Main text",
            web_scraper._html_to_text("<h1>Title</h1><script>bad()</script><p>Main text</p>"),
        )


if __name__ == "__main__":
    unittest.main()
