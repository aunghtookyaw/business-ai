import unittest
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

from scripts import receive_payment_server
from tools import veggies_production_portal as portal
from tools.veggies_production import CropDefinition


CROPS = [
    CropDefinition("zucchini", "Zucchini", "Zucchini", crop_id=1, category="Fruit Vegetables"),
    CropDefinition("rosemary", "Rosemary", "Rosemary", crop_id=2, category="Herbs and Specialty Crops"),
]
FARM_AREAS = [
    {"id": 1, "area_code": "HOME_FARM", "area_name": "Home Farm"},
    {"id": 2, "area_code": "NORTH_FARM", "area_name": "North Farm"},
]


def empty_search(filters):
    return [], {"total_records": 0, "page": 1, "total_pages": 1}


def record():
    return {
        "id": 7,
        "production_date": date(2026, 7, 14),
        "farm_area_id": 1,
        "farm_area": "Home Farm",
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


class ReadCursor:
    def __init__(self, rows=None, row=None):
        self.rows = rows or []
        self.row = row
        self.executions = []

    def __enter__(self): return self
    def __exit__(self, *args): return False
    def execute(self, sql, params=None): self.executions.append((sql, params))
    def fetchall(self): return self.rows
    def fetchone(self): return self.row


class ReadConnection:
    def __init__(self, cursor):
        self.read_cursor = cursor
        self.closed = False

    def cursor(self, **kwargs): return self.read_cursor
    def close(self): self.closed = True


class VeggiesProductionPortalTest(unittest.TestCase):
    def setUp(self):
        self.client = receive_payment_server.app.test_client()
        self.today_patcher = patch.object(portal, "today_summary", return_value={
            "total_quantity": Decimal("0"), "submission_count": 0, "crop_count": 0,
            "latest_entry_time": None, "unit_pending": True,
        })
        self.today_patcher.start()
        self.addCleanup(self.today_patcher.stop)
        self.area_patcher = patch.object(portal, "portal_farm_areas", return_value=FARM_AREAS)
        self.area_patcher.start()
        self.addCleanup(self.area_patcher.stop)

    def test_page_loads_and_crop_fields_come_from_master(self):
        with patch.object(portal, "portal_crops", return_value=CROPS), patch.object(portal, "search_records", side_effect=empty_search):
            response = self.client.get("/veggies-production")
        self.assertEqual(200, response.status_code)
        html = response.get_data(as_text=True)
        self.assertIn("<h1>Veggies Production Basic</h1>", html)
        self.assertIn('name="crop_zucchini"', html)
        self.assertIn('name="crop_rosemary"', html)
        self.assertIn('name="farm_area_id"', html)
        self.assertIn("Home Farm", html)
        self.assertIn("Farm Area", html)
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
                "farm_area_id": "1",
                "assignee": "Aye Aye", "crop_zucchini": "0", "crop_rosemary": "0.5",
                "submission_token": "4d98eecb-c4de-4c09-b176-cbe80770cb25",
            })
        self.assertEqual(303, response.status_code)
        self.assertEqual([Decimal("0"), Decimal("0.5")], [item["quantity"] for item in captured["items"]])

    def test_blank_quantity_creates_no_item(self):
        cleaned, errors = portal.validate_submission({"production_date": "2026-07-14", "farm_area_id": "1", "crop_zucchini": "", "crop_rosemary": "2"}, CROPS, FARM_AREAS)
        self.assertFalse(errors)
        self.assertEqual(["rosemary"], [item["crop_code"] for item in cleaned["items"]])

    def test_negative_quantity_is_rejected_beside_crop(self):
        with patch.object(portal, "portal_crops", return_value=CROPS), patch.object(portal, "search_records", side_effect=empty_search):
            response = self.client.post("/veggies-production", data={"production_date": "2026-07-14", "farm_area_id": "1", "crop_zucchini": "-1"})
        self.assertIn("Zucchini quantity cannot be negative", response.get_data(as_text=True))

    def test_missing_date_and_no_crop_are_rejected(self):
        cleaned, errors = portal.validate_submission({"production_date": "", "farm_area_id": "", "crop_zucchini": ""}, CROPS, FARM_AREAS)
        self.assertIsNone(cleaned["production_date"])
        self.assertIn("production_date", errors)
        self.assertIn("crops", errors)

    def test_save_transaction_rolls_back_on_failure(self):
        connection = FailingConnection()
        with self.assertRaisesRegex(RuntimeError, "insert failed"):
            portal.save_submission({
                "production_date": date(2026, 7, 14), "assignee": None, "note": None,
                "farm_area_id": 1,
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
            response = self.client.get("/veggies-production?date_from=2026-07-01&date_to=2026-07-31&production_date=2026-07-14&farm_area_id=1&assignee=Aye&crop=zucchini")
        self.assertEqual(200, response.status_code)
        self.assertEqual("2026-07-01", seen[0]["date_from"])
        self.assertEqual("Aye", seen[0]["assignee"])
        self.assertEqual("1", seen[0]["farm_area_id"])
        self.assertEqual("zucchini", seen[0]["crop"])

    def test_search_query_groups_all_selected_batch_and_area_fields(self):
        rows = [
            {"id": 7, "production_date": date(2026, 7, 14), "farm_area_id": 1,
             "farm_area": "Home Farm", "assignee": "Aye", "note": "",
             "entry_date": date(2026, 7, 14), "total_quantity": Decimal("3.5"),
             "crop_count": 2, "created_at": None, "updated_at": None,
             "filtered_count": 2},
            {"id": 8, "production_date": date(2026, 7, 14), "farm_area_id": 2,
             "farm_area": "North Farm", "assignee": "Mya", "note": "",
             "entry_date": date(2026, 7, 14), "total_quantity": Decimal("4.0"),
             "crop_count": 1, "created_at": None, "updated_at": None,
             "filtered_count": 2},
        ]
        cursor = ReadCursor(rows=rows)
        connection = ReadConnection(cursor)
        with patch.object(portal, "_connect", return_value=connection):
            result, summary = portal.search_records({})
        sql, params = cursor.executions[0]
        group_by = sql.split("GROUP BY", 1)[1].split(") filtered", 1)[0]
        for expression in (
            "batch.id", "batch.production_date", "batch.farm_area_id", "area.area_name",
            "batch.assignee", "batch.note", "batch.entry_date",
            "batch.created_at", "batch.updated_at",
        ):
            self.assertIn(expression, group_by)
        self.assertEqual(["Home Farm", "North Farm"], [row["farm_area"] for row in result])
        self.assertEqual(Decimal("3.5"), result[0]["total_quantity"])
        self.assertEqual(2, result[0]["crop_count"])
        self.assertEqual(2, summary["total_records"])
        self.assertEqual([portal.PAGE_SIZE, 0], params)
        self.assertTrue(connection.closed)

    def test_search_date_area_and_crop_filters_remain_parameterized(self):
        cursor = ReadCursor(rows=[])
        with patch.object(portal, "_connect", return_value=ReadConnection(cursor)):
            portal.search_records({
                "date_from": "2026-07-01", "date_to": "2026-07-31",
                "production_date": "2026-07-14", "farm_area_id": "2",
                "crop": "zucchini",
            })
        sql, params = cursor.executions[0]
        self.assertIn("batch.production_date >= %s", sql)
        self.assertIn("batch.production_date <= %s", sql)
        self.assertIn("batch.production_date = %s", sql)
        self.assertIn("batch.farm_area_id = %s", sql)
        self.assertIn("crop.crop_code = %s", sql)
        self.assertNotIn("2026-07-14", sql)
        self.assertEqual(
            ["2026-07-01", "2026-07-31", "2026-07-14", "2", "zucchini",
             portal.PAGE_SIZE, 0],
            params,
        )

    def test_today_summary_preserves_totals_submission_and_crop_counts(self):
        self.today_patcher.stop()
        expected = {
            "total_quantity": Decimal("12.5"), "submission_count": 2,
            "crop_count": 3, "latest_entry_time": datetime(2026, 7, 14, 9),
            "unit_pending": True,
        }
        cursor = ReadCursor(row=expected)
        result = portal.today_summary(connection=ReadConnection(cursor))
        self.today_patcher.start()
        sql, params = cursor.executions[0]
        self.assertEqual(expected, result)
        self.assertIn("SUM(item.quantity)", sql)
        self.assertIn("COUNT(DISTINCT batch.id)", sql)
        self.assertIn("COUNT(DISTINCT item.crop_id)", sql)
        self.assertIn("batch.created_at::date = CURRENT_DATE", sql)
        self.assertIsNone(params)

    def test_detail_view_lists_record_and_items(self):
        with patch.object(portal, "get_record", return_value=record()):
            response = self.client.get("/veggies-production/7")
        html = response.get_data(as_text=True)
        self.assertEqual(200, response.status_code)
        self.assertIn("Production record #7", html)
        self.assertIn("Morning harvest", html)
        self.assertIn("Home Farm", html)
        self.assertIn("Zucchini", html)
        self.assertIn("2.5", html)

    def test_quantities_display_with_one_decimal_without_rounding_edit_values(self):
        precise = record()
        precise["items"][0]["quantity"] = Decimal("2.5678")
        with patch.object(portal, "get_record", return_value=precise):
            detail_html = self.client.get("/veggies-production/7").get_data(as_text=True)
        with patch.object(portal, "portal_crops", return_value=CROPS), patch.object(portal, "get_record", return_value=precise):
            edit_html = self.client.get("/veggies-production/7/edit").get_data(as_text=True)
        self.assertIn("2.6", detail_html)
        self.assertNotIn("2.5678", detail_html)
        self.assertIn('value="2.5678"', edit_html)

    def test_edit_requires_confirmation_then_updates(self):
        updates = []
        with patch.object(portal, "portal_crops", return_value=CROPS), patch.object(portal, "get_record", return_value=record()), patch.object(portal, "update_submission", side_effect=lambda batch_id, values: updates.append((batch_id, values))):
            unconfirmed = self.client.post("/veggies-production/7/edit", data={"production_date": "2026-07-15", "farm_area_id": "1", "crop_zucchini": "3"})
            confirmed = self.client.post("/veggies-production/7/edit", data={"production_date": "2026-07-15", "farm_area_id": "1", "crop_zucchini": "3", "confirm_changes": "yes"})
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
               "farm_area_id": 1, "farm_area": "Home Farm",
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

    def test_farm_area_migration_is_additive_reversible_and_seeds_expected_areas(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1] / "migrations"
        up = (root / "20260715_004_veggies_farm_areas_up.sql").read_text()
        down = (root / "20260715_004_veggies_farm_areas_down.sql").read_text()
        self.assertIn("CREATE TABLE IF NOT EXISTS public.veggies_farm_area_master", up)
        self.assertIn("ADD COLUMN IF NOT EXISTS farm_area_id", up)
        self.assertIn("'HOME_FARM', 'Home Farm'", up)
        self.assertIn("ALTER COLUMN farm_area_id SET NOT NULL", up)
        self.assertNotIn("farm_production", up)
        self.assertIn("DROP COLUMN IF EXISTS farm_area_id", down)

    def test_manual_production_delete_is_atomic_and_imports_are_protected(self):
        connection=MagicMock();cursor=connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.side_effect=[{"id":7,"import_id":None},{"id":7}]
        result=portal.delete_submission(7,"7","test cleanup",connection=connection)
        self.assertTrue(result["deleted"]);connection.commit.assert_called_once()
        statements="\n".join(str(call.args[0]) for call in cursor.execute.call_args_list)
        self.assertIn("veggies_production_items",statements);self.assertIn("veggies_production_batches",statements)
        blocked=MagicMock();blocked.cursor.return_value.__enter__.return_value.fetchone.return_value={"id":7,"import_id":4}
        with self.assertRaisesRegex(ValueError,"Imported production records"):
            portal.delete_submission(7,"7","test cleanup",connection=blocked)
        blocked.rollback.assert_called_once()

    def test_production_detail_has_guarded_delete_form(self):
        with patch.object(portal,"get_record",return_value=record()):
            html=self.client.get("/veggies-production/7").get_data(as_text=True)
        self.assertIn("Delete Production Record",html)
        self.assertIn('name="confirmation"',html)
        self.assertIn('name="reason"',html)


if __name__ == "__main__":
    unittest.main()
