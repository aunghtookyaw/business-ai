import os
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from scripts import dashboard_server
from tools import dashboard_service, formula_engine


class DashboardOperationsTest(unittest.TestCase):
    def test_responsive_farm_selectors_preserve_controls_and_readability(self):
        root = Path(__file__).resolve().parents[1]
        html = (root / "dashboard-prototype/index.html").read_text()
        app = (root / "dashboard-prototype/app.js").read_text()
        css = (root / "dashboard-prototype/styles.css").read_text()
        for control in ("farmFieldToggle", "farmFieldApply", "farmVegetableToggle", "farmVegetableApply", "farmCropSearch", "farmSelectAll", "farmClearAll"):
            self.assertIn(f'id="{control}"', html)
        self.assertIn('matchMedia("(max-width: 768px)")', app)
        self.assertIn("applyFarmSelector", app)
        self.assertIn("updateFarmSelectorSummaries", app)
        self.assertIn("@media (max-width: 768px)", css)
        self.assertIn("min-height:44px", css)
        self.assertIn("grid-template-columns:repeat(2,minmax(0,1fr))", css)
        self.assertIn("max-height:none", css)
        self.assertIn("overflow-wrap:anywhere", css)
        self.assertIn(".farm-point-marker { r:2px", css)

    def test_farm_filters_validate_dates_ids_and_grouping(self):
        filters = dashboard_service.parse_farm_production_filters({"filters": {
            "start_date": "2026-01-01", "end_date": "2026-07-12",
            "crop_ids": [2, 1, 2], "farm_area_ids": [5], "grouping": "weekly",
        }})
        self.assertEqual(date(2026, 1, 1), filters.start_date)
        self.assertEqual((1, 2), filters.crop_ids)
        self.assertEqual((5,), filters.farm_area_ids)
        self.assertEqual("weekly", filters.grouping)
        with self.assertRaisesRegex(ValueError, "grouping"):
            dashboard_service.parse_farm_production_filters({"filters": {
                "start_date": "2026-01-01", "end_date": "2026-01-02", "grouping": "yearly",
            }})

    @patch("tools.dashboard_service.formula_engine.farm_production_analytics")
    @patch("tools.dashboard_service.formula_engine.farm_production_dimensions")
    def test_crop_defaults_only_when_selection_is_omitted(self, dimensions, trend):
        dimensions.return_value = {"crops": [{"id": value} for value in range(1, 8)], "farm_areas": []}
        trend.return_value = {"rows": [], "totals": [], "last_data_date": None}
        omitted = dashboard_service.parse_farm_production_filters({"filters": {
            "start_date": "2026-01-01", "end_date": "2026-01-02",
        }})
        dashboard_service.farm_production_dashboard(omitted)
        self.assertEqual((1, 2, 3, 4, 5), trend.call_args.args[2])
        cleared = dashboard_service.parse_farm_production_filters({"filters": {
            "start_date": "2026-01-01", "end_date": "2026-01-02", "crop_ids": [],
        }})
        dashboard_service.farm_production_dashboard(cleared)
        self.assertEqual((), trend.call_args.args[2])

    @patch("tools.formula_engine._fetch_all")
    @patch("tools.formula_engine.farm_production_trend")
    def test_all_fields_combines_crop_totals_and_keeps_units_separate(self, trend, fetch_all):
        trend.return_value = {
            "rows": [
                {"production_date": date(2026, 7, 1), "crop_id": 1, "crop_name": "Beetroot", "farm_area_id": 1, "farm_area": "Home Farm", "unit": "kg", "quantity": Decimal("4")},
                {"production_date": date(2026, 7, 1), "crop_id": 1, "crop_name": "Beetroot", "farm_area_id": 2, "farm_area": "North Farm", "unit": "kg", "quantity": Decimal("6")},
                {"production_date": date(2026, 7, 1), "crop_id": 1, "crop_name": "Beetroot", "farm_area_id": 2, "farm_area": "North Farm", "unit": "bunch", "quantity": Decimal("3")},
            ], "totals": [{"unit": "kg", "quantity": Decimal("10")}, {"unit": "bunch", "quantity": Decimal("3")}], "last_data_date": date(2026, 7, 1),
        }
        fetch_all.side_effect = [[], [
            {"crop_id": 1, "crop_name": "Beetroot", "unit": "kg", "quantity": Decimal("10"), "latest_production_date": date(2026, 7, 1)},
            {"crop_id": 1, "crop_name": "Beetroot", "unit": "bunch", "quantity": Decimal("3"), "latest_production_date": date(2026, 7, 1)},
        ], []]
        result = formula_engine.farm_production_analytics(
            date(2026, 7, 1), date(2026, 7, 7), [1], (), "daily", [],
        )
        self.assertEqual([Decimal("3"), Decimal("10")], sorted(row["quantity"] for row in result["combined_rows"]))
        self.assertEqual({"bunch", "kg"}, {row["unit"] for row in result["summary_by_crop"]})
        self.assertEqual("All Fields", result["combined_rows"][0]["farm_area"])

    @patch("tools.formula_engine._fetch_all")
    @patch("tools.formula_engine.farm_production_trend")
    def test_single_and_multiple_field_filters_and_empty_fields(self, trend, fetch_all):
        trend.return_value = {"rows": [], "totals": [], "last_data_date": None}
        fetch_all.side_effect = [[], [], []]
        areas = [{"id": 1, "area_name": "Home Farm"}, {"id": 2, "area_name": "North Farm"}]
        result = formula_engine.farm_production_analytics(
            date(2026, 7, 1), date(2026, 7, 2), [1], [1, 2], "daily", areas,
        )
        self.assertEqual([1, 2], trend.call_args.args[3])
        self.assertEqual({1, 2}, {row["farm_area_id"] for row in result["summary_by_area"]})
        self.assertTrue(all(row["crop_count"] == 0 for row in result["summary_by_area"]))
        self.assertEqual([1, 2], fetch_all.call_args_list[0].args[1]["farm_area_ids"])
        fetch_all.side_effect = [[], [], []]
        single = formula_engine.farm_production_analytics(
            date(2026, 7, 1), date(2026, 7, 2), [1], [1], "daily", areas,
        )
        self.assertEqual([1], trend.call_args.args[3])
        self.assertEqual([1], [row["farm_area_id"] for row in single["summary_by_area"]])

    @patch("tools.formula_engine._fetch_all")
    @patch("tools.formula_engine.farm_production_trend")
    def test_previous_period_comparison(self, trend, fetch_all):
        trend.return_value = {"rows": [], "totals": [], "last_data_date": None}
        fetch_all.side_effect = [[], [{"crop_id": 1, "crop_name": "A", "unit": "kg", "quantity": Decimal("15"), "latest_production_date": date(2026, 7, 7)}], [{"crop_id": 1, "unit": "kg", "quantity": Decimal("10")}]]
        result = formula_engine.farm_production_analytics(
            date(2026, 7, 1), date(2026, 7, 7), [1], [1], "daily", [],
        )
        self.assertEqual(Decimal("50"), result["summary_by_crop"][0]["percentage_change"])
        self.assertEqual(date(2026, 6, 24), result["previous_period"]["start_date"])
        self.assertEqual(date(2026, 6, 30), result["previous_period"]["end_date"])

    @patch("tools.dashboard_service.formula_engine.farm_production_analytics")
    @patch("tools.dashboard_service.formula_engine.farm_production_dimensions")
    def test_master_changes_are_returned_dynamically(self, dimensions, analytics):
        dimensions.return_value = {"crops": [{"id": 91, "crop_name": "New Crop"}], "farm_areas": [{"id": 12, "area_name": "New Field"}]}
        analytics.return_value = {"rows": [], "combined_rows": [], "totals": [], "summary_by_area": [], "summary_by_crop": []}
        filters = dashboard_service.parse_farm_production_filters({"filters": {"start_date": "2026-01-01", "end_date": "2026-01-02"}})
        result = dashboard_service.farm_production_dashboard(filters)
        self.assertEqual("New Crop", result["available_crops"][0]["crop_name"])
        self.assertEqual("New Field", result["available_farm_areas"][0]["area_name"])

    @patch("tools.formula_engine._fetch_all")
    def test_farm_trend_filters_and_keeps_mixed_unit_totals_separate(self, fetch_all):
        fetch_all.side_effect = [[
            {"production_date": date(2026, 1, 1), "crop_id": 1, "crop_name": "A",
             "farm_area_id": 9, "farm_area": "Home Farm", "unit": "kg", "quantity": Decimal("2")},
            {"production_date": date(2026, 1, 1), "crop_id": 1, "crop_name": "A",
             "farm_area_id": 9, "farm_area": "Home Farm", "unit": "bunch", "quantity": Decimal("3")},
        ], [{"last_data_date": date(2026, 1, 1)}]]
        result = formula_engine.farm_production_trend(
            date(2026, 1, 1), date(2026, 1, 31), [1], [9], "monthly"
        )
        sql = fetch_all.call_args_list[0].args[0]
        params = fetch_all.call_args_list[0].args[1]
        self.assertIn("DATE_TRUNC('month'", sql)
        self.assertIn("crop.id = ANY", sql)
        self.assertIn("area.id = ANY", sql)
        self.assertEqual([{"unit": "bunch", "quantity": Decimal("3")}, {"unit": "kg", "quantity": Decimal("2")}], result["totals"])

    @patch("tools.formula_engine._fetch_all")
    def test_empty_production_period(self, fetch_all):
        fetch_all.side_effect = [[], [{"last_data_date": None}]]
        result = formula_engine.farm_production_trend(date(2026, 1, 1), date(2026, 1, 2))
        self.assertEqual([], result["rows"])
        self.assertEqual([], result["totals"])

    @patch("tools.formula_engine._fetch_all", return_value=[])
    @patch("tools.formula_engine.sotephwar_inventory_stock")
    def test_inventory_groups_store_and_dynamic_bottle_types(self, stock, _fetch):
        stock.return_value = {"stock": [
            {"store": "Home", "product": "Sote Phwar 4L", "stock_qty": 7},
            {"store": "Home", "product": "Sote Phwar 500 mL", "stock_qty": 11},
            {"store": "North", "product": "SotePhwar 4 L", "stock_qty": 3},
        ]}
        result = formula_engine.sotephwar_inventory_dashboard()
        self.assertEqual(["4 L", "500 mL"], result["bottle_types"])
        self.assertEqual(10, next(row["current_quantity"] for row in result["bottle_totals"] if row["bottle_type"] == "4 L"))
        self.assertEqual(18, next(row["current_quantity"] for row in result["store_totals"] if row["store"] == "Home"))

    def test_new_dashboard_apis_require_authentication(self):
        client = dashboard_server.app.test_client()
        farm = client.post("/api/dashboard/farm-production", json={"filters": {}})
        inventory = client.get("/api/dashboard/inventory")
        payments = client.post("/api/dashboard/payments", json={"filters": {}})
        self.assertEqual(401, farm.status_code)
        self.assertEqual(401, inventory.status_code)
        self.assertEqual(401, payments.status_code)

    @patch.dict(os.environ, {"MASTER_USERNAME": "master", "MASTER_PASSWORD": "secret", "DASHBOARD_COOKIE_SECURE": "0"})
    @patch("scripts.dashboard_server.dashboard_service.inventory_dashboard", side_effect=RuntimeError("unavailable"))
    def test_inventory_api_failure_state(self, _inventory):
        client = dashboard_server.app.test_client()
        self.assertEqual(200, client.post("/api/auth/login", json={"username": "master", "password": "secret"}).status_code)
        response = client.get("/api/dashboard/inventory")
        self.assertEqual(500, response.status_code)
        self.assertFalse(response.get_json()["ok"])


if __name__ == "__main__":
    unittest.main()
