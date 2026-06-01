import unittest

import business_agent
from tools import formula_engine


class BusinessAgentRoutingTest(unittest.TestCase):
    def test_machinary_equipment_routes_to_category_summary(self):
        self.assertEqual(
            "category_summary",
            business_agent.choose_formula("what category is machinary equipment"),
        )

    def test_category_question_routes_to_category_summary(self):
        self.assertEqual(
            "category_summary",
            business_agent.choose_formula("show category summary this month"),
        )

    def test_subgroup_question_routes_to_category_summary(self):
        self.assertEqual(
            "category_summary",
            business_agent.choose_formula("show transection group by subgroup"),
        )

    def test_farm_filter_is_detected(self):
        self.assertEqual(
            {"sector": "Farm"},
            formula_engine.extract_dimension_filters("show farm expense this month"),
        )

    def test_extension_agrochemical_filters_are_detected(self):
        self.assertEqual(
            {"sector": "SP Extension", "category": "Agrochemicals"},
            formula_engine.extract_dimension_filters("extension agrochemical expense"),
        )

    def test_sotephwar_filter_maps_to_sp_production(self):
        self.assertEqual(
            {"sector": "SP Production"},
            formula_engine.extract_dimension_filters("sotephwar profit"),
        )

    def test_dynamic_sector_filter_is_detected_from_database_values(self):
        formula_engine.clear_dimension_value_cache()
        original_fetch_one = formula_engine._fetch_one
        formula_engine._fetch_one = lambda sql, params=None: {
            "income_expenses": [],
            "sectors": ["Retail Shop"],
            "categories": [],
            "item_descriptions": [],
            "payment_methods": [],
        }

        try:
            self.assertEqual(
                {"sector": "Retail Shop"},
                formula_engine.extract_dimension_filters("retail shop sales this month"),
            )
        finally:
            formula_engine._fetch_one = original_fetch_one
            formula_engine.clear_dimension_value_cache()

    def test_dynamic_category_filter_is_detected_from_database_values(self):
        formula_engine.clear_dimension_value_cache()
        original_fetch_one = formula_engine._fetch_one
        formula_engine._fetch_one = lambda sql, params=None: {
            "income_expenses": [],
            "sectors": [],
            "categories": ["Seed & Fertilizer"],
            "item_descriptions": [],
            "payment_methods": [],
        }

        try:
            self.assertEqual(
                {"category": "Seed & Fertilizer"},
                formula_engine.extract_dimension_filters("seed fertilizer expense this month"),
            )
        finally:
            formula_engine._fetch_one = original_fetch_one
            formula_engine.clear_dimension_value_cache()

    def test_dynamic_item_description_filter_is_detected_from_database_values(self):
        formula_engine.clear_dimension_value_cache()
        original_fetch_one = formula_engine._fetch_one
        formula_engine._fetch_one = lambda sql, params=None: {
            "income_expenses": [],
            "sectors": [],
            "categories": [],
            "item_descriptions": ["Diesel Fuel"],
            "payment_methods": [],
        }

        try:
            self.assertEqual(
                {"item_description": "Diesel Fuel"},
                formula_engine.extract_dimension_filters("diesel fuel expense this month"),
            )
        finally:
            formula_engine._fetch_one = original_fetch_one
            formula_engine.clear_dimension_value_cache()

    def test_dynamic_payment_method_filter_is_detected_from_database_values(self):
        formula_engine.clear_dimension_value_cache()
        original_fetch_one = formula_engine._fetch_one
        formula_engine._fetch_one = lambda sql, params=None: {
            "income_expenses": [],
            "sectors": [],
            "categories": [],
            "item_descriptions": [],
            "payment_methods": ["M-Pay"],
        }

        try:
            self.assertEqual(
                {"payment_method": "M-Pay"},
                formula_engine.extract_dimension_filters("m pay expense this month"),
            )
        finally:
            formula_engine._fetch_one = original_fetch_one
            formula_engine.clear_dimension_value_cache()


if __name__ == "__main__":
    unittest.main()
