import unittest

from tools.master_relink import filter_plan_to_transaction_ids, plan_relinks


class MasterRelinkPlanTest(unittest.TestCase):
    def test_plan_relinks_uses_normalized_master_match(self):
        plan = plan_relinks(
            transaction_rows=[
                {"id": 1, "value": "Factory 2 set up cost"},
                {"id": 2, "value": "Factory_2_Set-Up_Cost"},
                {"id": 3, "value": "Unknown Category"},
                {"id": 4, "value": ""},
            ],
            master_rows=[
                {"id": 10, "value": "Factory 2 Setup Cost"},
            ],
            existing_links=[],
        )

        self.assertEqual(4, plan.total)
        self.assertEqual(2, plan.matched)
        self.assertEqual(1, plan.unmatched)
        self.assertEqual(1, plan.blank)
        self.assertEqual(((1, 10), (2, 10)), plan.to_insert)
        self.assertEqual((("Unknown Category", 1),), plan.unmatched_values)

    def test_plan_relinks_skips_already_linked_rows(self):
        plan = plan_relinks(
            transaction_rows=[{"id": 1, "value": "Pwint Aung Kyaw POL"}],
            master_rows=[{"id": 20, "value": "Pwint Aung Kyaw Pol"}],
            existing_links=[{"transaction_id": 1, "master_id": 20}],
        )

        self.assertEqual(1, plan.matched)
        self.assertEqual(1, plan.already_linked)
        self.assertEqual((), plan.to_insert)

    def test_plan_relinks_reports_conflict_without_second_link(self):
        plan = plan_relinks(
            transaction_rows=[{"id": 1, "value": "Pwint Aung Kyaw POL"}],
            master_rows=[{"id": 20, "value": "Pwint Aung Kyaw Pol"}],
            existing_links=[{"transaction_id": 1, "master_id": 99}],
        )

        self.assertEqual(1, plan.matched)
        self.assertEqual((), plan.to_insert)
        self.assertEqual(
            {
                "transaction_id": 1,
                "value": "Pwint Aung Kyaw POL",
                "target_master_id": 20,
                "existing_master_ids": [99],
            },
            plan.conflicts[0],
        )

    def test_plan_relinks_blocks_duplicate_master_names(self):
        plan = plan_relinks(
            transaction_rows=[{"id": 1, "value": "Factory 2 setup cost"}],
            master_rows=[
                {"id": 10, "value": "Factory 2 Setup Cost"},
                {"id": 11, "value": "Factory 2 Set Up Cost"},
            ],
            existing_links=[],
        )

        self.assertEqual(0, plan.matched)
        self.assertEqual(1, plan.unmatched)
        self.assertEqual("factory 2 setup cost", plan.duplicate_master_names[0][0])

    def test_filter_plan_to_transaction_ids_limits_insert_pairs(self):
        plan = plan_relinks(
            transaction_rows=[
                {"id": 1, "value": "Factory 2 setup cost"},
                {"id": 2, "value": "Factory 2 setup cost"},
            ],
            master_rows=[{"id": 10, "value": "Factory 2 Setup Cost"}],
            existing_links=[],
        )

        filtered = filter_plan_to_transaction_ids(plan, [2])

        self.assertEqual(((2, 10),), filtered.to_insert)


if __name__ == "__main__":
    unittest.main()
