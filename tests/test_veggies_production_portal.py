import unittest
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

from scripts import receive_payment_server
from tools import veggies_production_portal as portal
from tools.veggies_production import CropDefinition


CROPS = [
    CropDefinition("zucchini", "Zucchini", "Zucchini", crop_id=1),
    CropDefinition("rosemary", "Rosemary", "Rosemary", crop_id=2),
]


def empty_search(filters):
    return [], {"total_quantity": Decimal("0"), "submission_count": 0, "crop_count": 0, "latest_date": None}


def record():
    return {
        "id": 7,
        "production_date": date(2026, 7, 14),
        "assignee": "Aye Aye",
        "note": "Morning harvest",
        "ai_note": "Review quality",
        "entry_date": date(2026, 7, 14),
        "created_at": datetime(2026, 7, 14, 8, 0),
        "updated_at": datetime(2026, 7, 14, 8, 0),
        "items": [{
            "crop_id": 1,
            "crop_code": "zucchini",
            "crop_name": "Zucchini",
            "quantity": Decimal("2.5"),
            "unit": None,
            "created_at": datetime(2026, 7, 14, 8, 0),
            "updated_at": datetime(2026, 7, 14, 8, 0),
        }],
    }


class FailingCursor:
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def execute(self, sql, params=None): raise RuntimeError("insert failed")


class FailingConnection:
    def __init__(self): self.rolled_back = False
    def cursor(self, **kwargs): return FailingCursor()
    def rollback(self): self.rolled_back = True
    def close(self): pass


class VeggiesProductionPortalTest(unittest.TestCase):
    def setUp(self):
        self.client = receive_payment_server.app.test_client()

    def test_page_loads_and_crop_fields_come_from_master(self):
        with patch.object(portal, "portal_crops", return_value=CROPS), patch.object(portal, "search_records", side_effect=empty_search):
            response = self.client.get("/veggies-production")
        self.assertEqual(200, response.status_code)
        html = response.get_data(as_text=True)
        self.assertIn("<h1>Veggies Production Basic</h1>", html)
        self.assertIn('name="crop_zucchini"', html)
        self.assertIn('name="crop_rosemary"', html)
        self.assertNotIn("Farm Area", html)

    def test_valid_submission_accepts_decimal_blank_and_explicit_zero(self):
        captured = {}
        def fake_save(values):
            captured.update(values)
            return {"id": 9}
        with patch.object(portal, "portal_crops", return_value=CROPS), patch.object(portal, "search_records", side_effect=empty_search), patch.object(portal, "save_submission", side_effect=fake_save):
            response = self.client.post("/veggies-production", data={
                "production_date": "2026-07-14", "entry_date": "2026-07-14",
                "assignee": "Aye Aye", "crop_zucchini": "0", "crop_rosemary": "0.5",
                "submission_token": "4d98eecb-c4de-4c09-b176-cbe80770cb25",
            })
        self.assertEqual(303, response.status_code)
        self.assertEqual([Decimal("0"), Decimal("0.5")], [item["quantity"] for item in captured["items"]])

    def test_blank_quantity_creates_no_item(self):
        cleaned, errors = portal.validate_submission({"production_date": "2026-07-14", "crop_zucchini": "", "crop_rosemary": "2"}, CROPS)
        self.assertFalse(errors)
        self.assertEqual(["rosemary"], [item["crop_code"] for item in cleaned["items"]])

    def test_negative_quantity_is_rejected_beside_crop(self):
        with patch.object(portal, "portal_crops", return_value=CROPS), patch.object(portal, "search_records", side_effect=empty_search):
            response = self.client.post("/veggies-production", data={"production_date": "2026-07-14", "crop_zucchini": "-1"})
        self.assertIn("Zucchini quantity cannot be negative", response.get_data(as_text=True))

    def test_missing_date_and_no_crop_are_rejected(self):
        cleaned, errors = portal.validate_submission({"production_date": "", "crop_zucchini": ""}, CROPS)
        self.assertIsNone(cleaned["production_date"])
        self.assertIn("production_date", errors)
        self.assertIn("crops", errors)

    def test_save_transaction_rolls_back_on_failure(self):
        connection = FailingConnection()
        with self.assertRaisesRegex(RuntimeError, "insert failed"):
            portal.save_submission({
                "production_date": date(2026, 7, 14), "assignee": None, "note": None,
                "ai_note": None, "entry_date": date(2026, 7, 14), "submission_token": "token",
                "items": [{"crop_id": 1, "quantity": Decimal("1"), "unit": None}],
            }, connection=connection)
        self.assertTrue(connection.rolled_back)

    def test_search_filters_date_assignee_and_crop(self):
        seen = []
        def fake_search(filters):
            seen.append(filters)
            return empty_search(filters)
        with patch.object(portal, "portal_crops", return_value=CROPS), patch.object(portal, "search_records", side_effect=fake_search):
            response = self.client.get("/veggies-production?date_from=2026-07-01&date_to=2026-07-31&production_date=2026-07-14&assignee=Aye&crop=zucchini")
        self.assertEqual(200, response.status_code)
        self.assertEqual("2026-07-01", seen[0]["date_from"])
        self.assertEqual("Aye", seen[0]["assignee"])
        self.assertEqual("zucchini", seen[0]["crop"])

    def test_detail_view_lists_record_and_items(self):
        with patch.object(portal, "get_record", return_value=record()):
            response = self.client.get("/veggies-production/7")
        html = response.get_data(as_text=True)
        self.assertEqual(200, response.status_code)
        self.assertIn("Production record #7", html)
        self.assertIn("Morning harvest", html)
        self.assertIn("Zucchini", html)
        self.assertIn("2.5", html)

    def test_edit_requires_confirmation_then_updates(self):
        updates = []
        with patch.object(portal, "portal_crops", return_value=CROPS), patch.object(portal, "get_record", return_value=record()), patch.object(portal, "update_submission", side_effect=lambda batch_id, values: updates.append((batch_id, values))):
            unconfirmed = self.client.post("/veggies-production/7/edit", data={"production_date": "2026-07-15", "crop_zucchini": "3"})
            confirmed = self.client.post("/veggies-production/7/edit", data={"production_date": "2026-07-15", "crop_zucchini": "3", "confirm_changes": "yes"})
        self.assertIn("Confirm the changes", unconfirmed.get_data(as_text=True))
        self.assertEqual(303, confirmed.status_code)
        self.assertEqual(7, updates[0][0])
        self.assertEqual(Decimal("3"), updates[0][1]["items"][0]["quantity"])

    def test_migrations_never_modify_legacy_farm_production(self):
        from pathlib import Path
        migration = (Path(__file__).resolve().parents[1] / "migrations" / "20260714_002_veggies_production_portal_up.sql").read_text()
        self.assertNotIn("farm_production", migration)
        self.assertNotIn("farm_transection", migration)


if __name__ == "__main__":
    unittest.main()
