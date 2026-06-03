import unittest
from unittest.mock import patch

import family_ai_bot
from tools import live_info
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
        with patch.object(family_ai_bot, "live_info_context", return_value=None):
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

        with patch.object(family_ai_bot, "live_info_context", return_value=None):
            with patch.object(family_ai_bot, "scrape_urls_from_text", return_value=scrape_result):
                with patch.object(family_ai_bot, "ask_ai", return_value="answer") as ask_ai:
                    answer = family_ai_bot.ask_family_ai("summarize https://example.com")

        self.assertEqual("answer", answer)
        self.assertIn("Web page content:", ask_ai.call_args.args[0])
        self.assertIn("Example page text", ask_ai.call_args.args[0])

    def test_ask_family_ai_uses_local_ai_for_live_agriculture_advice(self):
        live_context = {
            "type": "weather",
            "question": "Yangon weather today",
            "place": "Yangon",
            "days": [],
            "source": "Open-Meteo",
        }

        with patch.object(family_ai_bot, "live_info_context", return_value=live_context):
            with patch.object(family_ai_bot, "ask_ai", return_value="farm advice") as ask_ai:
                answer = family_ai_bot.ask_family_ai("Yangon weather today")

        self.assertEqual("farm advice", answer)
        ask_ai.assert_called_once()
        self.assertIn("agricultural use", ask_ai.call_args.args[0])
        self.assertIn("include each forecast day", ask_ai.call_args.args[0])
        self.assertIn("Do not summarize away the actual live rows", ask_ai.call_args.args[0])
        self.assertIn("Open-Meteo", ask_ai.call_args.args[0])

    def test_ask_family_ai_falls_back_to_direct_live_answer_when_local_ai_fails(self):
        live_context = {
            "type": "weather",
            "question": "Yangon weather today",
            "place": "Yangon",
            "forecast_days": 1,
            "current": {
                "condition": "partly cloudy",
                "temperature_c": 30,
                "humidity_percent": 70,
                "rain_now_mm": 0,
            },
            "days": [{
                "date": "2026-06-03",
                "max_c": 33,
                "min_c": 25,
                "rain_probability_percent": 20,
            }],
            "source": "Open-Meteo",
        }

        with patch.object(family_ai_bot, "live_info_context", return_value=live_context):
            with patch.object(family_ai_bot, "ask_ai", side_effect=RuntimeError("offline")):
                answer = family_ai_bot.ask_family_ai("Yangon weather today")

        self.assertIn("Weather for Yangon", answer)
        self.assertIn("Source: Open-Meteo", answer)

    def test_weather_answer_uses_open_meteo(self):
        class FakeResponse:
            def __init__(self, data):
                self._data = data

            def raise_for_status(self):
                return None

            def json(self):
                return self._data

        responses = [
            FakeResponse({
                "results": [{
                    "name": "Yangon",
                    "admin1": "Yangon",
                    "country": "Myanmar",
                    "latitude": 16.8,
                    "longitude": 96.15,
                }],
            }),
            FakeResponse({
                "current": {
                    "temperature_2m": 30,
                    "relative_humidity_2m": 70,
                    "precipitation": 0,
                    "weather_code": 2,
                },
                "daily": {
                    "temperature_2m_max": [33],
                    "temperature_2m_min": [25],
                    "precipitation_probability_max": [20],
                },
            }),
        ]

        with patch.object(live_info.requests, "get", side_effect=responses):
            answer = live_info.get_weather_answer("Yangon weather today")

        self.assertIn("Weather for Yangon, Yangon, Myanmar", answer)
        self.assertIn("Temperature: 30 C", answer)
        self.assertIn("Source: Open-Meteo", answer)

    def test_weather_location_before_keyword_is_detected(self):
        self.assertEqual("Yangon", live_info._extract_location("Yangon weather today"))
        self.assertEqual("Yangon", live_info._extract_location("Yangon 7 day forecast"))

    def test_weather_forecast_days_are_detected(self):
        self.assertEqual(2, live_info._forecast_days("Yangon weather tomorrow"))
        self.assertEqual(7, live_info._forecast_days("Yangon 7 day forecast"))

    def test_seven_day_forecast_answer_uses_daily_rows(self):
        class FakeResponse:
            def __init__(self, data):
                self._data = data

            def raise_for_status(self):
                return None

            def json(self):
                return self._data

        responses = [
            FakeResponse({
                "results": [{
                    "name": "Yangon",
                    "admin1": "Yangon",
                    "country": "Myanmar",
                    "latitude": 16.8,
                    "longitude": 96.15,
                }],
            }),
            FakeResponse({
                "current": {
                    "temperature_2m": 30,
                    "relative_humidity_2m": 70,
                    "precipitation": 0,
                    "weather_code": 2,
                },
                "daily": {
                    "time": ["2026-06-03", "2026-06-04"],
                    "weather_code": [2, 61],
                    "temperature_2m_max": [33, 31],
                    "temperature_2m_min": [25, 24],
                    "precipitation_probability_max": [20, 80],
                },
            }),
        ]

        with patch.object(live_info.requests, "get", side_effect=responses):
            answer = live_info.get_weather_answer("Yangon 7 day forecast")

        self.assertIn("Weather forecast for Yangon, Yangon, Myanmar", answer)
        self.assertIn("2026-06-03", answer)
        self.assertIn("2026-06-04", answer)

    def test_vegetable_price_answer_converts_thb_to_mmk(self):
        rows = [
            {
                "name": "มะเขือเทศ",
                "price_thb": 20.0,
                "unit": "kg",
                "source": "https://example.com/prices",
            },
        ]

        with patch.object(live_info, "_fetch_price_rows", return_value=(rows, [])):
            with patch.object(live_info, "get_thb_mmk_rate", return_value=(80.0, "test-date")):
                answer = live_info.get_vegetable_price_answer("Thailand tomato price in MMK")

        self.assertIn("1 THB = 80.00 MMK", answer)
        self.assertIn("20.00 THB/kg ~= 1,600 MMK/kg", answer)
        self.assertIn("https://example.com/prices", answer)

    def test_market_negotiation_answer_includes_thailand_and_myanmar_rows(self):
        thai_rows = [
            {
                "name": "ผักกาดขาว",
                "price_thb": 25.0,
                "unit": "kg",
                "source": "https://example.com/thailand",
            },
        ]
        myanmar_rows = [
            {
                "name": "Lettuce",
                "price_mmk_min": 1000.0,
                "price_mmk_max": 4000.0,
                "unit": "kg",
                "source": "https://example.com/myanmar",
            },
        ]

        with patch.object(live_info, "_fetch_price_rows", return_value=(thai_rows, [])):
            with patch.object(live_info, "_fetch_myanmar_price_rows", return_value=(myanmar_rows, [])):
                with patch.object(live_info, "get_thb_mmk_rate", return_value=(80.0, "test-date")):
                    answer = live_info.answer_live_info("Makro lettuce deal price negotiation")

        self.assertIn("Makro price negotiation signal", answer)
        self.assertIn("25.00 THB/kg ~= 2,000 MMK/kg", answer)
        self.assertIn("1,000-4,000 MMK/kg", answer)
        self.assertIn("Do not reduce supplied product/quality", answer)

    def test_market_negotiation_context_warns_when_exact_thai_match_is_missing(self):
        thai_rows = [
            {
                "name": "มะเขือเทศ",
                "price_thb": 20.0,
                "unit": "kg",
                "source": "https://example.com/thailand",
            },
        ]

        with patch.object(live_info, "_fetch_price_rows", return_value=(thai_rows, [])):
            with patch.object(live_info, "_fetch_myanmar_price_rows", return_value=([], [])):
                with patch.object(live_info, "get_thb_mmk_rate", return_value=(80.0, "test-date")):
                    context = live_info.live_info_context("Makro lettuce deal price negotiation")

        self.assertEqual("market_negotiation", context["type"])
        self.assertIn("No exact Thailand match", "\n".join(context["notes"]))
        self.assertEqual("มะเขือเทศ", context["thailand_rows"][0]["name"])

    def test_ask_family_ai_prompt_mentions_makro_negotiation_rules(self):
        live_context = {
            "type": "market_negotiation",
            "question": "Makro lettuce deal price negotiation",
            "exchange_rate": {"rate": 80.0, "date": "test-date"},
            "thailand_rows": [],
            "myanmar_rows": [],
            "sources": {},
        }

        with patch.object(family_ai_bot, "live_info_context", return_value=live_context):
            with patch.object(family_ai_bot, "ask_ai", return_value="negotiation advice") as ask_ai:
                answer = family_ai_bot.ask_family_ai("Makro lettuce deal price negotiation")

        self.assertEqual("negotiation advice", answer)
        self.assertIn("retail seller negotiation", ask_ai.call_args.args[0])
        self.assertIn("product reduction risk", ask_ai.call_args.args[0])
        self.assertIn("Do not summarize away the actual live rows", ask_ai.call_args.args[0])

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
