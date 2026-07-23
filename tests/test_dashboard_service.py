import unittest
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from tools import dashboard_service, formula_engine
from tools.veggies_production import CropDefinition


class DashboardServiceTest(unittest.TestCase):
    def test_farm_unit_resolver_prefers_master_then_record_then_unspecified(self):
        master = [
            {"id": 1, "crop_code": "ZUCCHINI", "crop_name": "Zucchini", "default_unit": "Kg"},
            {"id": 2, "crop_code": "ROSEMARY", "crop_name": "Rosemary", "default_unit": None},
        ]
        definitions = [
            CropDefinition("ZUCCHINI", "Zucchini", "Courgette", crop_id=1, default_unit="Kg"),
            CropDefinition("ROSEMARY", "Rosemary", "Rosemary", crop_id=2),
        ]
        resolver, by_id = dashboard_service._farm_crop_resolver(master, definitions)

        blank = dashboard_service._resolve_farm_row(
            {"crop_id": 1, "crop_name": "Zucchini", "unit": " "}, resolver, by_id,
        )
        fallback = dashboard_service._resolve_farm_row(
            {"crop_code": "ROSEMARY", "crop_name": "Rosemary", "unit": "Bunch"}, resolver, by_id,
        )
        unresolved = dashboard_service._resolve_farm_row(
            {"crop_name": "Missing Crop", "unit": None}, resolver, by_id,
        )

        self.assertEqual("Kg", blank["unit"])
        self.assertEqual("Bunch", fallback["unit"])
        self.assertEqual("Unspecified", unresolved["unit"])

    def test_farm_crop_resolver_matches_code_normalized_name_and_alias(self):
        master = [{
            "id": 7, "crop_code": "GREEN_LOLLO_LETTUCE",
            "crop_name": "Green Lollo Lettuce", "default_unit": "Kg",
        }]
        definitions = [
            CropDefinition(
                "GREEN_LOLLO_LETTUCE", "Green Lollo Lettuce", "Green lollo",
                crop_id=7, default_unit="Kg",
            ),
        ]
        resolver, by_id = dashboard_service._farm_crop_resolver(master, definitions)

        for row in (
            {"crop_code": "GREEN_LOLLO_LETTUCE"},
            {"crop_name": "  green   lollo lettuce "},
            {"crop_name": "Green lollo"},
        ):
            with self.subTest(row=row):
                resolved = dashboard_service._resolve_farm_row(row, resolver, by_id)
                self.assertEqual("GREEN_LOLLO_LETTUCE", resolved["crop_code"])
                self.assertEqual("Green Lollo Lettuce", resolved["crop_name"])
                self.assertEqual("Kg", resolved["unit"])

    @patch("tools.dashboard_service.load_crop_definitions")
    def test_farm_dashboard_resolves_units_without_changing_quantities(self, definitions):
        definitions.return_value = [
            CropDefinition("ZUCCHINI", "Zucchini", "Courgette", crop_id=1, default_unit="Kg"),
            CropDefinition("HERB", "Herb", "Herb", crop_id=2, default_unit="Bunch"),
        ]
        dimensions = {
            "crops": [
                {"id": 1, "crop_code": "ZUCCHINI", "crop_name": "Zucchini", "default_unit": "Kg"},
                {"id": 2, "crop_code": "HERB", "crop_name": "Herb", "default_unit": "Bunch"},
            ],
            "farm_areas": [{"id": 3, "area_name": "Home Farm"}],
        }
        trend = {
            "rows": [
                {"production_date": date(2026, 7, 1), "crop_id": 1, "crop_name": "zucchini",
                 "farm_area_id": 3, "farm_area": "Home Farm", "unit": None, "quantity": Decimal("124")},
                {"production_date": date(2026, 7, 1), "crop_id": 2, "crop_name": "Herb",
                 "farm_area_id": 3, "farm_area": "Home Farm", "unit": "", "quantity": Decimal("3")},
            ],
            "combined_rows": [], "summary_by_area": [], "summary_by_crop": [],
            "totals": [], "last_data_date": date(2026, 7, 1),
        }
        filters = dashboard_service.FarmProductionFilters(
            date(2026, 7, 1), date(2026, 7, 1), (1, 2), (), "daily",
        )
        with patch("tools.dashboard_service.formula_engine.farm_production_dimensions",
                   return_value=dimensions), patch(
            "tools.dashboard_service.formula_engine.farm_production_analytics",
            return_value=trend,
        ):
            result = dashboard_service.farm_production_dashboard(filters)

        self.assertEqual(Decimal("127"), sum(row["quantity"] for row in result["combined_rows"]))
        self.assertEqual({"Kg", "Bunch"}, {row["unit"] for row in result["combined_rows"]})
        self.assertEqual("Mixed units", result["summary"]["total_unit"])
        self.assertEqual("Kg", result["daily_stacked"][0]["crop_units"]["Zucchini"])
        self.assertEqual("Mixed units", result["daily_stacked"][0]["total_unit"])
        self.assertEqual(
            Decimal("127"),
            sum(row["quantity"] for row in result["combined_rows"]),
        )
        self.assertEqual(2, len(result["crop_totals"]))

    @patch("tools.dashboard_service.load_crop_definitions")
    @patch("tools.dashboard_service.formula_engine.farm_production_analytics")
    @patch("tools.dashboard_service.formula_engine.farm_production_dimensions")
    def test_farm_empty_summary_uses_selected_master_unit(
            self, dimensions, analytics, definitions):
        dimensions.return_value = {
            "crops": [{
                "id": 1, "crop_code": "ZUCCHINI", "crop_name": "Zucchini",
                "default_unit": "Kg",
            }],
            "farm_areas": [],
        }
        definitions.return_value = [
            CropDefinition("ZUCCHINI", "Zucchini", "Zucchini", crop_id=1, default_unit="Kg"),
        ]
        analytics.return_value = {
            "rows": [], "combined_rows": [], "summary_by_area": [],
            "summary_by_crop": [], "totals": [], "last_data_date": None,
        }
        filters = dashboard_service.FarmProductionFilters(
            date(2026, 7, 1), date(2026, 7, 31), (1,), (), "daily",
        )

        result = dashboard_service.farm_production_dashboard(filters)

        self.assertEqual(0, result["summary"]["total_quantity"])
        self.assertEqual("Kg", result["summary"]["unit"])
        self.assertEqual(0, result["summary"]["active_crop_count"])
        self.assertEqual(0, result["crop_totals"][0]["quantity"])
        self.assertEqual("Kg", result["crop_totals"][0]["unit"])

    @patch("tools.dashboard_service.load_crop_definitions")
    @patch("tools.dashboard_service.formula_engine.farm_production_analytics")
    @patch("tools.dashboard_service.formula_engine.farm_production_dimensions")
    def test_farm_summary_respects_crop_field_period_and_scope_filters(
            self, dimensions, analytics, definitions):
        dimensions.return_value = {
            "crops": [{
                "id": 1, "crop_code": "ZUCCHINI", "crop_name": "Zucchini",
                "default_unit": "Kg",
            }],
            "farm_areas": [{"id": 9, "area_name": "Home Farm"}],
        }
        definitions.return_value = [
            CropDefinition("ZUCCHINI", "Zucchini", "Zucchini", crop_id=1, default_unit="Kg"),
        ]
        analytics.return_value = {
            "rows": [{
                "production_date": date(2026, 7, 1),
                "crop_id": 1, "crop_name": "Zucchini",
                "farm_area_id": 9, "farm_area": "Home Farm",
                "unit": None, "quantity": Decimal("12"),
            }],
            "combined_rows": [], "summary_by_area": [], "summary_by_crop": [],
            "totals": [], "last_data_date": date(2026, 7, 1),
        }
        filters = dashboard_service.FarmProductionFilters(
            date(2026, 7, 1), date(2026, 7, 31), (1,), (9,), "daily",
            "Farm", "farm",
        )

        result = dashboard_service.farm_production_dashboard(filters)

        analytics.assert_called_once_with(
            date(2026, 7, 1), date(2026, 7, 31), (1,), (9,), "daily",
            dimensions.return_value["farm_areas"],
        )
        self.assertEqual(12, result["summary"]["total_quantity"])
        self.assertEqual(12, result["daily_stacked"][0]["total"])
        self.assertEqual(Decimal("12"), result["crop_totals"][0]["quantity"])

        incompatible = dashboard_service.FarmProductionFilters(
            date(2026, 7, 1), date(2026, 7, 31), (1,), (9,), "daily",
            "Sote Phwar", "",
        )
        empty = dashboard_service.farm_production_dashboard(incompatible)
        self.assertEqual(0, empty["summary"]["total_quantity"])
        self.assertEqual("Kg", empty["summary"]["unit"])
        self.assertEqual(1, analytics.call_count)
    @patch("tools.dashboard_service.formula_engine.farm_production_analytics")
    @patch("tools.dashboard_service.formula_engine.farm_production_dimensions")
    def test_farm_dashboard_omits_field_chart_payload_but_keeps_period_composition(
            self, dimensions, trend):
        dimensions.return_value = {
            "crops": [{"id": 1, "crop_name": "Tomato"}],
            "farm_areas": [{"id": 2, "area_name": "Home Farm"}],
        }
        trend.return_value = {
            "rows": [{
                "production_date": date(2026, 7, 1),
                "crop_name": "Tomato",
                "farm_area": "Home Farm",
                "quantity": 12.5,
            }],
            "combined_rows": [],
            "summary_by_area": [],
            "summary_by_crop": [],
            "totals": [],
        }
        filters = dashboard_service.FarmProductionFilters(
            date(2026, 7, 1), date(2026, 7, 31), (1,), (), "daily",
        )

        result = dashboard_service.farm_production_dashboard(filters)

        self.assertNotIn("field_stacked", result)
        self.assertNotIn("field_totals", result)
        self.assertEqual(31, len(result["daily_stacked"]))
        self.assertEqual("1 Jul", result["daily_stacked"][0]["label"])
        self.assertEqual("31 Jul", result["daily_stacked"][-1]["label"])
        self.assertEqual(12.5, result["daily_stacked"][0]["total"])
        self.assertEqual(0, result["daily_stacked"][1]["total"])
        self.assertEqual(0, result["daily_stacked"][1]["crops"]["Tomato"])
        self.assertEqual("Home Farm", result["summary"]["top_field"])

    @patch("tools.dashboard_service.formula_engine.farm_production_analytics")
    @patch("tools.dashboard_service.formula_engine.farm_production_dimensions")
    def test_farm_daily_timeline_covers_full_multi_month_range(
            self, dimensions, analytics):
        dimensions.return_value = {
            "crops": [{"id": 1, "crop_name": "Tomato"}],
            "farm_areas": [],
        }
        analytics.return_value = {
            "rows": [], "combined_rows": [], "summary_by_area": [],
            "summary_by_crop": [], "totals": [],
        }
        filters = dashboard_service.FarmProductionFilters(
            date(2026, 6, 1), date(2026, 7, 31), (1,), (), "daily",
        )

        result = dashboard_service.farm_production_dashboard(filters)

        self.assertEqual(61, len(result["daily_stacked"]))
        self.assertEqual("2026-06-01", result["daily_stacked"][0]["period"])
        self.assertEqual("2026-07-31", result["daily_stacked"][-1]["period"])
        self.assertTrue(all(row["total"] == 0 for row in result["daily_stacked"]))

    @patch("tools.dashboard_service.formula_engine.farm_production_analytics")
    @patch("tools.dashboard_service.formula_engine.farm_production_dimensions")
    def test_farm_monthly_timeline_uses_canonical_month_buckets_through_latest_data(
            self, dimensions, analytics):
        dimensions.return_value = {
            "crops": [{"id": 1, "crop_name": "Tomato"}],
            "farm_areas": [],
        }
        analytics.return_value = {
            "rows": [
                {"production_date": date(2026, 1, 1), "crop_name": "Tomato", "quantity": 10},
                {"production_date": date(2026, 7, 1), "crop_name": "Tomato", "quantity": 20},
            ],
            "last_data_date": date(2026, 7, 22),
            "combined_rows": [], "summary_by_area": [], "summary_by_crop": [], "totals": [],
        }
        filters = dashboard_service.FarmProductionFilters(
            date(2026, 1, 1), date(2026, 12, 31), (1,), (), "monthly",
        )

        with patch(
            "tools.dashboard_service.formula_engine.farm_production_trend",
            return_value={"rows": [
                {"production_date": date(2026, 1, 5)},
                {"production_date": date(2026, 1, 6)},
                {"production_date": date(2026, 7, 22)},
            ]},
        ):
            result = dashboard_service.farm_production_dashboard(filters)

        self.assertEqual("monthly", result["bucket_grouping"])
        self.assertEqual(7, len(result["daily_stacked"]))
        self.assertEqual(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul"],
                         [row["label"] for row in result["daily_stacked"]])
        self.assertEqual(30, sum(row["total"] for row in result["daily_stacked"]))
        self.assertEqual(3, result["summary"]["production_day_count"])
        self.assertEqual(date(2026, 7, 22), result["summary"]["latest_production_date"])

    @patch("tools.dashboard_service.formula_engine.farm_production_analytics")
    @patch("tools.dashboard_service.formula_engine.farm_production_dimensions")
    def test_farm_weekly_timeline_uses_one_bucket_per_week(
            self, dimensions, analytics):
        dimensions.return_value = {
            "crops": [{"id": 1, "crop_name": "Tomato"}],
            "farm_areas": [],
        }
        analytics.return_value = {
            "rows": [], "combined_rows": [], "summary_by_area": [],
            "summary_by_crop": [], "totals": [],
        }
        filters = dashboard_service.FarmProductionFilters(
            date(2026, 6, 1), date(2026, 7, 30), (1,), (), "weekly",
        )

        result = dashboard_service.farm_production_dashboard(filters)

        self.assertEqual("weekly", result["bucket_grouping"])
        self.assertEqual(9, len(result["daily_stacked"]))
        self.assertEqual("2026-06-01", result["daily_stacked"][0]["period"])
        self.assertEqual("2026-07-27", result["daily_stacked"][-1]["period"])

    def setUp(self):
        dashboard_service.clear_dashboard_cache()

    def test_parse_dashboard_filters_validates_period_and_status(self):
        filters = dashboard_service.parse_dashboard_filters({
            "filters": {
                "period": {"type": "month", "year": 2026, "month": 6},
                "sector": "Sote Phwar",
                "business_unit": "sote_phwar",
                "payment_status": "Partial",
            }
        })

        self.assertEqual("month:2026-06", dashboard_service.legacy_period(filters.period))
        self.assertEqual("Sote Phwar", filters.sector)
        self.assertEqual("Partial", filters.payment_status)

        with self.assertRaisesRegex(ValueError, "payment_status"):
            dashboard_service.parse_dashboard_filters({
                "filters": {
                    "period": {"type": "year", "year": 2026},
                    "payment_status": "Deleted",
                }
            })

    @patch("tools.dashboard_service.formula_engine.sotephwar_production_inventory_dashboard")
    def test_inventory_year_defaults_to_latest_authoritative_month(self, report):
        def payload(year=None, month=None):
            selected = int(month or 7)
            return {
                "selected_year": int(year or 2026), "selected_month": selected,
                "monthly_production": [
                    {"month": "2026-05", "total_production": 10},
                    {"month": "2026-07", "total_production": 20},
                ],
            }
        report.side_effect = payload
        result = dashboard_service.inventory_dashboard(year=2026)
        self.assertEqual(7, result["selected_month"])
        self.assertEqual([5, 7], result["available_production_months"])
        self.assertEqual("July 2026", result["production_summary_label"])

    @patch("tools.dashboard_service.formula_engine.sotephwar_production_inventory_dashboard")
    def test_inventory_explicit_empty_month_does_not_fallback(self, report):
        report.return_value = {
            "selected_year": 2026, "selected_month": 6,
            "monthly_production": [{"month": "2026-07", "total_production": 20}],
        }
        result = dashboard_service.inventory_dashboard(year=2026, month=6)
        self.assertEqual(6, result["selected_month"])
        self.assertFalse(result["production_summary_has_data"])
        self.assertEqual("June 2026", result["production_summary_label"])

    @patch("tools.dashboard_service._trend_periods", return_value=[("Jun", "month:2026-06")])
    @patch("tools.dashboard_service.formula_engine.list_transactions")
    @patch("tools.dashboard_service.formula_engine.recent_payment_receipts")
    @patch("tools.dashboard_service.formula_engine.top_expense_categories")
    @patch("tools.dashboard_service.formula_engine.sotephwar_product_ranking")
    @patch("tools.dashboard_service.formula_engine.top_income")
    @patch("tools.dashboard_service.formula_engine.calculate_inventory_value")
    @patch("tools.dashboard_service.formula_engine.payment_receive_summary")
    @patch("tools.dashboard_service.formula_engine.sales_total")
    @patch("tools.dashboard_service.formula_engine.cash_flow")
    @patch("tools.dashboard_service.formula_engine.kpi_overview")
    def test_executive_dashboard_passes_through_canonical_values(
        self,
        kpi,
        cash,
        sales,
        receivables,
        inventory,
        top_customers,
        top_products,
        expense_categories,
        payments,
        transactions,
        _trend_periods,
    ):
        kpi.return_value = {
            "total_income": 1000,
            "total_expense": 400,
            "net_profit": 600,
            "profit_margin_percent": 60,
        }
        cash.return_value = {"total_inflow": 700, "total_outflow": 400, "net_cash_flow": 300}
        sales.return_value = {
            "amount_received": 700, "outstanding_amount": 300,
            "transection_income_rows": [{"amount": 1000}],
            "sources": {"farm_invoice_count": 1, "sotephwar_invoice_count": 0},
        }
        receivables.return_value = {
            "outstanding_receivables": 300,
            "collection_rate_percent": 70,
            "total_received": 700,
        }
        inventory.return_value = {
            "total_inventory_value": 160000,
            "stock": [
                {
                    "store": "A",
                    "product": "Sote Phwar 1L",
                    "stock_qty": 5,
                    "unit_cost": 32000,
                    "inventory_value": 160000,
                }
            ],
            "locations": [{"store": "A", "qty": 5, "inventory_value": 160000}],
        }
        top_customers.return_value = {"income": [{"customer_name": "C", "total_amount": 1000}]}
        top_products.return_value = {"products": [{"product": "P", "quantity": 5}]}
        expense_categories.return_value = {"categories": [{"category": "E", "amount": 400}]}
        payments.return_value = {"payments": [{"id": 1, "receive_amount": 100}]}
        transactions.return_value = {"transactions": [{"id": 2, "amount": 50}]}
        filters = dashboard_service.parse_dashboard_filters({
            "filters": {"period": {"type": "year", "year": 2026}}
        })

        result, cached = dashboard_service.executive_dashboard(filters)

        self.assertFalse(cached)
        self.assertEqual(1000, result["metrics"]["revenue"])
        self.assertEqual(400, result["metrics"]["expenses"])
        self.assertEqual(600, result["metrics"]["net_profit"])
        self.assertEqual(700, result["metrics"]["cash_received"])
        self.assertEqual(300, result["metrics"]["outstanding_receivables"])
        self.assertEqual(160000, result["metrics"]["inventory_value"])
        self.assertEqual(5, result["metrics"]["inventory_bottles"])
        self.assertEqual(160000, result["inventory"]["locations"][0]["inventory_value"])
        self.assertEqual(1000, result["trend"][0]["revenue"])
        self.assertEqual(300, result["trend"][0]["cash_flow"])

    def test_trend_stops_at_last_real_period_and_preserves_internal_zero(self):
        rows = [
            {"label": "Jun", "has_source_data": True, "revenue": 100},
            {"label": "Jul", "has_source_data": True, "revenue": 0},
            {"label": "Aug", "has_source_data": False, "revenue": None},
            {"label": "Sep", "has_source_data": False, "revenue": None},
        ]
        result = dashboard_service._trim_trailing_missing_periods(rows)
        self.assertEqual(["Jun", "Jul"], [row["label"] for row in result])
        self.assertEqual(0, result[-1]["revenue"])

    def test_period_bucket_shapes_support_year_month_week_and_custom_ranges(self):
        year = dashboard_service._trend_periods({"type": "year", "year": 2026})
        month = dashboard_service._trend_periods({"type": "month", "year": 2026, "month": 7})
        week = dashboard_service._trend_periods({"type": "week", "start": "2026-07-20"})
        custom = dashboard_service._trend_periods({"type": "custom", "start": "2026-07-01", "end": "2026-07-22"})
        self.assertEqual(12, len(year))
        self.assertEqual("month:2026-12", year[-1][1])
        self.assertTrue(all(period.startswith("range:") for _, period in month))
        self.assertEqual(7, len(week))
        self.assertTrue(all(period.startswith("date:") for _, period in week))
        self.assertTrue(all(period.startswith("range:") for _, period in custom))

    def test_multiple_series_use_last_period_with_any_source_data(self):
        rows = [
            {"label": "May", "has_source_data": True, "revenue": 10, "expense": None, "profit": None},
            {"label": "Jun", "has_source_data": True, "revenue": None, "expense": 5, "profit": -5},
            {"label": "Jul", "has_source_data": False, "revenue": None, "expense": None, "profit": None},
        ]
        result = dashboard_service._trim_trailing_missing_periods(rows)
        self.assertEqual(["May", "Jun"], [row["label"] for row in result])

    def test_month_trailing_week_removed_and_partial_current_week_retained(self):
        rows = [
            {"label": "W1", "has_source_data": True, "revenue": 10, "expense": 2, "profit": 8},
            {"label": "W2", "has_source_data": True, "revenue": 0, "expense": 0, "profit": 0},
            {"label": "W3", "has_source_data": True, "revenue": 5, "expense": 1, "profit": 4},
            {"label": "W4", "has_source_data": True, "revenue": 1, "expense": 0, "profit": 1},
            {"label": "W5", "has_source_data": False, "revenue": None, "expense": None, "profit": None},
        ]
        result = dashboard_service._trim_trailing_missing_periods(rows)
        self.assertEqual(["W1", "W2", "W3", "W4"], [row["label"] for row in result])
        self.assertEqual(0, result[1]["revenue"])

    def test_historical_month_week_and_range_views_share_trailing_cutoff(self):
        for labels in (("W1", "W2", "W3", "W4", "W5"),
                       ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"),
                       ("01 Jul", "03 Jul", "05 Jul", "07 Jul")):
            rows = [{"label": label, "has_source_data": index < 3,
                     "revenue": index if index < 3 else None}
                    for index, label in enumerate(labels)]
            self.assertEqual(list(labels[:3]),
                             [row["label"] for row in dashboard_service._trim_trailing_missing_periods(rows)])

    @patch("tools.dashboard_service.formula_engine.sales_total")
    @patch("tools.dashboard_service.formula_engine.cash_flow")
    @patch("tools.dashboard_service.formula_engine.kpi_overview")
    def test_trend_row_distinguishes_real_zero_from_missing(self, kpi, cash, sales):
        kpi.return_value = {"total_income": 0, "total_expense": 0, "net_profit": 0}
        cash.return_value = {"net_cash_flow": 0}
        sales.return_value = {"outstanding_amount": 0, "transection_income_rows": [], "sources": {}}
        missing = dashboard_service._trend_row("Aug", "month:2026-08", {})
        sales.return_value["sources"] = {"farm_invoice_count": 1}
        genuine_zero = dashboard_service._trend_row("Jul", "month:2026-07", {})
        self.assertIsNone(missing["revenue"])
        self.assertEqual(0, genuine_zero["revenue"])

    def test_cached_dashboard_does_not_reexecute_loader(self):
        filters = dashboard_service.parse_dashboard_filters({
            "filters": {"period": {"type": "year", "year": 2026}}
        })
        calls = []

        def loader():
            calls.append(True)
            return {"ok": True}

        first, first_cached = dashboard_service._cached("test", filters, 30, loader)
        second, second_cached = dashboard_service._cached("test", filters, 30, loader)

        self.assertEqual(first, second)
        self.assertFalse(first_cached)
        self.assertTrue(second_cached)
        self.assertEqual(1, len(calls))

    @patch("tools.dashboard_service.formula_engine.recent_payment_receipts")
    @patch("tools.dashboard_service.formula_engine.payment_receive_summary")
    def test_payments_dashboard_uses_canonical_reports_and_labels_invoice_age(self, summary, receipts):
        summary.return_value = {
            "total_invoice_amount": 1000, "total_received": 400,
            "outstanding_receivables": 600, "collection_rate_percent": 40,
            "aging": {"0-30": 600}, "customer_balances": [{"customer": "C", "outstanding_balance": 600}],
            "sector_totals": [], "invoices": [{"received_amount": 400, "outstanding_balance": 600}],
        }
        receipts.return_value = {"payments": [{"id": 1, "receive_amount": 400}]}
        filters = dashboard_service.parse_dashboard_filters({"filters": {"period": {"type": "year", "year": 2026}}})
        result = dashboard_service.payments_dashboard(filters)
        self.assertEqual(600, result["metrics"]["outstanding"])
        self.assertEqual("Partial", result["invoices"][0]["payment_status"])
        self.assertIn("invoice age", result["data_quality"][0]["message"])
        summary.assert_called_once_with("year:2026", sector=None, customer=None, payment_status=None, limit=100)

    def test_payments_query_contract_is_frozen(self):
        self.assertEqual(
            {
                "version": "payments-v1-2026-07-16",
                "read_only": True,
                "voucher_identity": ["sector", "voucher_number", "invoice_date", "customer"],
                "period_basis": {"receivables": "invoice_date", "receipts": "receive_date"},
                "sources": ["payment_receive_summary", "recent_payment_receipts"],
                "row_limit": 100,
                "voucher_order": ["outstanding_balance DESC", "invoice_date ASC NULLS LAST"],
                "receipt_order": ["receive_date DESC NULLS LAST", "id DESC"],
                "aging_semantics": "invoice_age_not_due_date",
            },
            dashboard_service.PAYMENTS_QUERY_CONTRACT,
        )

    @patch("tools.formula_engine._fetch_all")
    @patch("tools.formula_engine.ensure_payment_receive_table")
    def test_live_payment_formula_sql_contract_keeps_identity_filters_and_ordering(self, _ensure, fetch_all):
        fetch_all.return_value = []
        formula_engine.payment_receive_summary(
            "year:2026", sector="Farm", customer="C", payment_status="Partial", limit=100,
        )
        summary_sql = fetch_all.call_args.args[0]
        self.assertIn("f.\"Invoice_Number\"::text", summary_sql)
        self.assertIn("f.\"Date\"", summary_sql)
        self.assertIn("invoices.customer", summary_sql)
        self.assertIn("p.\"Sector\" = invoices.sector", summary_sql)
        self.assertIn("p.\"Voucher_Number\" = invoices.voucher_number", summary_sql)
        self.assertIn("p.\"Invoice_Date\" = invoices.invoice_date", summary_sql)
        self.assertIn("ORDER BY outstanding_balance DESC", summary_sql)

        formula_engine.recent_payment_receipts(
            "year:2026", sector="Farm", customer="C", payment_status="Partial", limit=100,
        )
        receipt_sql = fetch_all.call_args.args[0]
        self.assertIn('"Receive_Date" AS receive_date', receipt_sql)
        self.assertIn('AND "Sector" = %(sector)s', receipt_sql)
        self.assertIn('COALESCE("Customer", \'\') = %(customer)s', receipt_sql)
        self.assertIn('ORDER BY "Receive_Date" DESC NULLS LAST, id DESC', receipt_sql)

    @patch("tools.dashboard_service.ask_ai", return_value="Executive Summary\n- Revenue is $10.")
    @patch("tools.dashboard_service.executive_dashboard")
    def test_qwen_narrative_rejects_numeric_or_currency_content(self, executive_dashboard, _ask_ai):
        executive_dashboard.return_value = ({
            "filter_label": "2026",
            "metrics": {},
            "cash_flow": {
                "total_inflow": 0,
                "total_outflow": 0,
                "net_cash_flow": 0,
            },
            "top_customers": [],
            "top_expense_categories": [],
            "data_quality": [],
        }, False)
        filters = dashboard_service.parse_dashboard_filters({
            "filters": {"period": {"type": "year", "year": 2026}}
        })

        with self.assertRaisesRegex(RuntimeError, "prohibited"):
            dashboard_service._build_executive_insight(filters)


if __name__ == "__main__":
    unittest.main()
