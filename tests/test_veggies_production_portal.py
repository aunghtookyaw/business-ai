import unittest
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

from scripts import receive_payment_server
from tools import veggies_production_portal as portal
from tools.veggies_production import CropDefinition


CROPS = [
    CropDefinition("zucchini", "Zucchini", "Zucchini", crop_id=1, category="Fruit Vegetables"),
    CropDefinition("rosemary", "Rosemary", "Rosemary", crop_id=2, category="Herbs and Specialty Crops"),
]


def empty_search(filters):
    return [], {"total_records": 0, "page": 1, "total_pages": 1}


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
            "category": "Fruit Vegetables",
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
        self.today_patcher = patch.object(portal, "today_summary", return_value={
            "total_quantity": Decimal("0"), "submission_count": 0, "crop_count": 0,
            "latest_entry_time": None, "unit_pending": True,
        })
        self.today_patcher.start()
        self.addCleanup(self.today_patcher.stop)

    def test_page_loads_and_crop_fields_come_from_master(self):
        with patch.object(portal, "portal_crops", return_value=CROPS), patch.object(portal, "search_records", side_effect=empty_search):
            response = self.client.get("/veggies-production")
        self.assertEqual(200, response.status_code)
        html = response.get_data(as_text=True)
        self.assertIn("<h1>Veggies Production Basic</h1>", html)
        self.assertIn('name="crop_zucchini"', html)
        self.assertIn('name="crop_rosemary"', html)
        self.assertNotIn("Farm Area", html)
        self.assertIn("Fruit Vegetables", html)
        self.assertIn("Herbs and Specialty Crops", html)

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

    def test_category_migration_maps_without_inserting_duplicate_crops(self):
        from pathlib import Path
        migration = (Path(__file__).resolve().parents[1] / "migrations" / "20260715_003_veggies_crop_categories_up.sql").read_text()
        self.assertIn("ADD COLUMN IF NOT EXISTS category", migration)
        self.assertIn("WHEN 'CHERRY_TOMATO' THEN 'Fruit Vegetables'", migration)
        self.assertIn("ELSE 'Other'", migration)
        self.assertIn("WHERE category IS NULL", migration)
        self.assertNotIn("INSERT INTO pipkgfu2wr9qxyy.veggies_crop_master", migration)
        from tools.veggies_production import default_crop_definitions
        codes = [crop.crop_code for crop in default_crop_definitions()]
        self.assertEqual(len(codes), len(set(codes)))

    def test_crop_search_entered_only_and_live_preview_are_browser_features(self):
        with patch.object(portal, "portal_crops", return_value=CROPS), patch.object(portal, "search_records", side_effect=empty_search):
            html = self.client.get("/veggies-production").get_data(as_text=True)
        self.assertIn('id="cropSearch"', html)
        self.assertIn("Entered Crops Only", html)
        self.assertIn('id="previewItems"', html)
        self.assertIn("input.value.trim()!==''", html)
        self.assertIn("items.push", html)

    def test_today_summary_cards_show_counts_time_and_pending_unit_note(self):
        self.today_patcher.stop()
        with patch.object(portal, "today_summary", return_value={
            "total_quantity": Decimal("245.5"), "submission_count": 3, "crop_count": 7,
            "latest_entry_time": datetime(2026, 7, 15, 9, 45, 2), "unit_pending": True,
        }), patch.object(portal, "portal_crops", return_value=CROPS), patch.object(portal, "search_records", side_effect=empty_search):
            html = self.client.get("/veggies-production").get_data(as_text=True)
        self.today_patcher.start()
        self.assertIn("Today’s Total Production", html)
        self.assertIn("245.5", html)
        self.assertIn("Today’s Number of Submissions", html)
        self.assertIn("Unit configuration pending", html)
        self.assertIn("09:45:02", html)

    def test_success_summary_contains_saved_business_values(self):
        with patch.object(portal, "portal_crops", return_value=CROPS), patch.object(portal, "search_records", side_effect=empty_search):
            response = self.client.get("/veggies-production?saved=1&saved_date=2026-07-15&saved_assignee=Aye&saved_crops=2&saved_total=3.5")
        html = response.get_data(as_text=True)
        self.assertIn("Veggies production saved successfully", html)
        self.assertIn("Number of Crops Saved: 2", html)
        self.assertIn("Total Quantity Saved: 3.5", html)

    def test_search_sorting_and_pagination_controls(self):
        row = {"id": 1, "production_date": date(2026, 7, 15), "assignee": "Aye",
               "total_quantity": Decimal("4"), "crop_count": 1, "note": "", "entry_date": date(2026, 7, 15)}
        seen = []
        def fake_search(filters):
            seen.append(filters)
            return [row], {"total_records": 26, "page": int(filters.get("page") or 1), "total_pages": 2}
        with patch.object(portal, "portal_crops", return_value=CROPS), patch.object(portal, "search_records", side_effect=fake_search):
            html = self.client.get("/veggies-production?sort=highest&page=1").get_data(as_text=True)
        self.assertEqual("highest", seen[0]["sort"])
        self.assertIn("Highest total quantity", html)
        self.assertIn(">Next</a>", html)
        self.assertIn(">Edit</a>", html)

    def test_inactive_historical_crop_remains_on_edit_page(self):
        historical = record()
        historical["items"].append({
            "crop_id": 99, "crop_code": "inactive_crop", "crop_name": "Inactive Crop",
            "category": "Other", "quantity": Decimal("1"), "unit": None,
            "created_at": datetime(2026, 7, 14, 8), "updated_at": datetime(2026, 7, 14, 8),
        })
        with patch.object(portal, "portal_crops", return_value=CROPS.copy()), patch.object(portal, "get_record", return_value=historical):
            html = self.client.get("/veggies-production/7/edit").get_data(as_text=True)
        self.assertIn("Inactive Crop", html)
        self.assertIn("You are editing an existing production record", html)
        self.assertIn("Original created time", html)

    def test_crop_master_supports_category_active_unit_and_order(self):
        master = [{"id": 1, "crop_code": "zucchini", "crop_name": "Zucchini",
                   "category": "Fruit Vegetables", "active": False, "default_unit": None,
                   "display_order": 10, "created_at": None, "updated_at": None}]
        with patch.object(portal, "list_crop_master", return_value=master):
            html = self.client.get("/veggies-production/crops").get_data(as_text=True)
        self.assertIn("Veggies Crop Master", html)
        self.assertIn("Fruit Vegetables", html)
        self.assertIn("Show on new entry form", html)
        self.assertNotIn('value="yes" checked', html)

    def test_migrations_never_modify_legacy_farm_production(self):
        from pathlib import Path
        migration = (Path(__file__).resolve().parents[1] / "migrations" / "20260714_002_veggies_production_portal_up.sql").read_text()
        self.assertNotIn("farm_production", migration)
        self.assertNotIn("farm_transection", migration)


if __name__ == "__main__":
    unittest.main()
