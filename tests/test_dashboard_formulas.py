import unittest

from tools import formula_engine


class DashboardFormulaTest(unittest.TestCase):
    def test_receivable_summary_groups_by_canonical_voucher_identity(self):
        captured = {}
        original_fetch_all = formula_engine._fetch_all
        original_ensure = formula_engine.ensure_payment_receive_table

        def fake_fetch_all(sql, params=None):
            captured["sql"] = sql
            return []

        formula_engine._fetch_all = fake_fetch_all
        formula_engine.ensure_payment_receive_table = lambda: None
        try:
            result = formula_engine.payment_receive_summary("year:2026")
        finally:
            formula_engine._fetch_all = original_fetch_all
            formula_engine.ensure_payment_receive_table = original_ensure

        self.assertEqual(0, result["outstanding_receivables"])
        self.assertIn('f."Date"', captured["sql"])
        self.assertIn('s."Invoice_Date"', captured["sql"])
        self.assertIn("LEFT JOIN LATERAL", captured["sql"])
        self.assertIn('COALESCE(p."Customer", \'\') = invoices.customer', captured["sql"])

    def test_product_ranking_normalizes_known_sotephwar_variants(self):
        captured = {}
        original_fetch_all = formula_engine._fetch_all

        def fake_fetch_all(sql, params=None):
            captured["sql"] = sql
            return []

        formula_engine._fetch_all = fake_fetch_all
        try:
            formula_engine.sotephwar_product_ranking("year:2026")
        finally:
            formula_engine._fetch_all = original_fetch_all

        self.assertIn("'sotephwar1l'", captured["sql"])
        self.assertIn("'Sote Phwar 1L'", captured["sql"])
        self.assertIn("ORDER BY quantity DESC", captured["sql"])


if __name__ == "__main__":
    unittest.main()
