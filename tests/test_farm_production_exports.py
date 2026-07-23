import tempfile
import unittest
from pathlib import Path

from openpyxl import load_workbook
from pypdf import PdfReader

from tools.farm_production_pdf import (
    write_farm_production_excel,
    write_farm_production_pdf,
)


class FarmProductionExportTest(unittest.TestCase):
    def setUp(self):
        self.payload = {
            "start_date": "2026-07-01",
            "end_date": "2026-07-31",
            "summary": {
                "total_production": 124,
                "total_unit": "Kg",
                "production_days": 1,
                "active_crops": 1,
                "top_field": "Home Farm",
                "top_crop": "Zucchini",
                "top_crop_unit": "Kg",
            },
            "daily_stacked": [{
                "period": "2026-07-01",
                "label": "1 Jul",
                "crops": {"Zucchini": 124},
                "crop_units": {"Zucchini": "Kg"},
                "total": 124,
                "total_unit": "Kg",
            }],
            "combined_rows": [{
                "production_date": "2026-07-01",
                "crop_code": "ZUCCHINI",
                "crop_name": "Zucchini",
                "farm_area": "Home Farm",
                "quantity": 124,
                "unit": "Kg",
            }],
        }

    def test_pdf_export_uses_resolved_crop_master_unit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "farm.pdf"
            write_farm_production_pdf(self.payload, path)
            text = "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)

        self.assertIn("124.00 Kg", text)
        self.assertIn("Zucchini (Kg)", text)
        self.assertNotIn("Unspecified", text)

    def test_excel_export_uses_resolved_crop_master_unit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "farm.xlsx"
            write_farm_production_excel(self.payload, path)
            workbook = load_workbook(path, data_only=True)
            summary_values = list(workbook["Summary"].values)
            record_values = list(workbook["Production Records"].values)

        self.assertIn(("Total Production", "124.00 Kg"), summary_values)
        self.assertEqual("ZUCCHINI", record_values[1][1])
        self.assertEqual(124, record_values[1][4])
        self.assertEqual("Kg", record_values[1][5])

