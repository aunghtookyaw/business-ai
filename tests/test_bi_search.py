import unittest

from tools import bi_search


class BISearchTest(unittest.TestCase):
    def test_customer_values_include_farm_transection_customers(self):
        original_fetch_all = bi_search._fetch_all

        def fake_fetch_all(sql, params=None):
            if "customer_master" in sql:
                return [{"value": "Pwint Aung Kyaw POL"}]
            if "Sotephwar_Transection" in sql:
                return [{"value": "Ma Shwe War"}]
            if "farm_transection" in sql:
                return [{"value": "Makro"}, {"value": "MAKRO"}]
            return []

        bi_search._fetch_all = fake_fetch_all
        try:
            values = bi_search.customer_values()
            matches = bi_search.search_customers("makro")
        finally:
            bi_search._fetch_all = original_fetch_all

        self.assertIn("Makro", values)
        self.assertEqual([{"value": "Makro", "score": 1.0}], matches)


if __name__ == "__main__":
    unittest.main()
