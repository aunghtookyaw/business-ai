import unittest
from datetime import date

from tools import google_calendar_client


class GoogleCalendarClientTest(unittest.TestCase):
    def test_event_body_uses_due_date_and_reminders(self):
        row = {
            "id": 12,
            "creditor": "Ma Gyi Moe",
            "amount": 3000000,
            "category": "Loan",
            "subcategory": "Investor Loan",
            "frequency": "Monthly",
            "status": "Active",
            "notes": "3% interest",
            "next_due_date": date(2026, 6, 9),
        }

        event = google_calendar_client._event_body(row)

        self.assertEqual("bigshotobl12", event["id"])
        self.assertIn("Ma Gyi Moe", event["summary"])
        self.assertEqual("2026-06-09", event["start"]["date"])
        self.assertEqual("2026-06-10", event["end"]["date"])
        self.assertEqual("business-ai", event["extendedProperties"]["private"]["source"])
        self.assertEqual(
            [10080, 4320, 1440],
            [item["minutes"] for item in event["reminders"]["overrides"]],
        )


if __name__ == "__main__":
    unittest.main()
