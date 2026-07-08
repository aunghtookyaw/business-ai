import unittest
from datetime import date

from scripts.import_excel_workbook import SHEETS
from tools.excel_importer import TABLES, _normalise_row


class ExcelImporterTest(unittest.TestCase):
    def test_farm_transection_table_maps_to_import_sheet(self):
        table = TABLES["farm_transection"]

        self.assertEqual("Farm_Transection", table["label"])
        self.assertEqual("Farm_Transection", SHEETS["farm_transection"])
        self.assertEqual(
            [
                "Date",
                "Customer",
                "Invoice_Number",
                "Total_Amount",
                "Total_Received",
                "Outstanding_Balance",
                "Note",
                "AI_Analysis",
            ],
            table["columns"],
        )

    def test_farm_transection_row_normalises_upload_values(self):
        cleaned = _normalise_row(
            TABLES["farm_transection"],
            {
                "Date": "2026-06-15",
                "Customer": "Ma Shwe War",
                "Invoice_Number": "12",
                "Total_Amount": "1,500,000",
                "Total_Received": "500000",
                "Note": "partial payment",
                "AI_Analysis": "",
            },
        )

        self.assertEqual(date(2026, 6, 15), cleaned["Date"])
        self.assertEqual("Ma Shwe War", cleaned["Customer"])
        self.assertEqual(12, cleaned["Invoice_Number"])
        self.assertEqual(1500000, cleaned["Total_Amount"])
        self.assertEqual(500000, cleaned["Total_Received"])
        self.assertEqual(1000000, cleaned["Outstanding_Balance"])
        self.assertEqual("partial payment", cleaned["Note"])
        self.assertIsNone(cleaned["AI_Analysis"])

    def test_farm_transection_zero_received_recalculates_outstanding_balance(self):
        cleaned = _normalise_row(
            TABLES["farm_transection"],
            {
                "Date": "2026-07-03",
                "Customer": "Good Food",
                "Invoice_Number": "71",
                "Total_Amount": "466000",
                "Total_Received": "0",
                "Outstanding_Balance": "0",
            },
        )

        self.assertEqual(466000, cleaned["Total_Amount"])
        self.assertEqual(0, cleaned["Total_Received"])
        self.assertEqual(466000, cleaned["Outstanding_Balance"])

    def test_farm_transection_rejects_over_received_amount(self):
        with self.assertRaisesRegex(ValueError, "Total_Received cannot be greater"):
            _normalise_row(
                TABLES["farm_transection"],
                {
                    "Date": "2026-07-03",
                    "Customer": "Good Food",
                    "Invoice_Number": "71",
                    "Total_Amount": "466000",
                    "Total_Received": "466001",
                },
            )


if __name__ == "__main__":
    unittest.main()
