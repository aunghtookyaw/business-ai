import unittest

from tools import master_data


class MasterDataNormalizationTest(unittest.TestCase):
    def test_category_normalization_handles_case_spaces_punctuation_and_setup(self):
        values = [
            "Factory 2 Set Up Cost",
            " Factory 2 set up cost ",
            "factory 2 set-up cost",
            "Factory_2_Setup_Cost",
        ]

        normalized = {master_data.normalize_name(value) for value in values}

        self.assertEqual({"factory 2 setup cost"}, normalized)

    def test_customer_normalization_handles_case_and_punctuation(self):
        values = [
            "Pwint Aung Kyaw POL",
            "Pwint Aung Kyaw Pol",
            "PWINT AUNG KYAW POL",
            "Pwint Aung Kyaw (POL)",
        ]

        normalized = {master_data.normalize_name(value) for value in values}

        self.assertEqual({"pwint aung kyaw pol"}, normalized)

    def test_customer_normalization_moves_comma_honorific_to_front(self):
        values = [
            "Ma Shwe War",
            "Shwe War,Ma",
            "Shwe War, Ma",
        ]

        normalized = {master_data.normalize_name(value) for value in values}

        self.assertEqual({"ma shwe war"}, normalized)

    def test_duplicate_groups_choose_highest_count_canonical(self):
        groups = master_data.duplicate_groups(
            [
                {"value": "Factory 2 Set up cost", "row_count": 62},
                {"value": "Factory 2 Set up Cost", "row_count": 44},
                {"value": "Fuel", "row_count": 10},
            ]
        )

        self.assertEqual(1, len(groups))
        self.assertEqual("factory 2 setup cost", groups[0].normalized_name)
        self.assertEqual("Factory 2 Set up cost", groups[0].canonical_value)
        self.assertEqual(106, groups[0].total_rows)
        self.assertEqual(
            [
                {"value": "Factory 2 Set up cost", "row_count": 62},
                {"value": "Factory 2 Set up Cost", "row_count": 44},
            ],
            groups[0].to_dict()["variants"],
        )

    def test_duplicate_groups_preserve_original_variant_text(self):
        groups = master_data.duplicate_groups(
            [
                {"value": "Marketing  and Promotion Expenses", "row_count": 6},
                {"value": "Marketing\xa0 and Promotion Expenses", "row_count": 3},
            ]
        )

        self.assertEqual(1, len(groups))
        self.assertEqual("marketing and promotion expenses", groups[0].normalized_name)
        self.assertEqual(
            [
                {"value": "Marketing  and Promotion Expenses", "row_count": 6},
                {"value": "Marketing\xa0 and Promotion Expenses", "row_count": 3},
            ],
            groups[0].to_dict()["variants"],
        )


if __name__ == "__main__":
    unittest.main()
