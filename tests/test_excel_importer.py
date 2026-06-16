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
                "Total_Due",
                "Paid",
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
                "Total_Due": "1,500,000",
                "Paid": "500000",
                "Note": "partial payment",
                "AI_Analysis": "",
            },
        )

        self.assertEqual(date(2026, 6, 15), cleaned["Date"])
        self.assertEqual("Ma Shwe War", cleaned["Customer"])
        self.assertEqual(12, cleaned["Invoice_Number"])
        self.assertEqual(1500000, cleaned["Total_Due"])
        self.assertEqual(500000, cleaned["Paid"])
        self.assertEqual("partial payment", cleaned["Note"])
        self.assertIsNone(cleaned["AI_Analysis"])


if __name__ == "__main__":
    unittest.main()
