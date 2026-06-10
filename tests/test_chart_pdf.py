import tempfile
import unittest
from pathlib import Path

from tools import chart_pdf
from tools.bi_reports import format_text_report


class ChartPdfTest(unittest.TestCase):
    def test_create_chart_pdf_report_writes_pdf(self):
        original_choose_formula = chart_pdf.choose_formula
        original_run_formula = chart_pdf.run_formula

        chart_pdf.choose_formula = lambda question: "kpi_overview"
        chart_pdf.run_formula = lambda formula_name, question: {
            "formula": "kpi_overview",
            "period": "this_month",
            "total_income": 1000,
            "total_expense": 400,
            "net_profit": 600,
            "profit_margin_percent": 60,
        }
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                output_path = Path(temp_dir) / "chart.pdf"

                created = chart_pdf.create_chart_pdf_report("this month kpi", output_path)

                self.assertTrue(created)
                self.assertTrue(output_path.read_bytes().startswith(b"%PDF"))
                self.assertGreater(output_path.stat().st_size, 1000)
                pdf_text = output_path.read_bytes().decode("latin-1")
                self.assertNotIn("Best method:", pdf_text)
                self.assertNotIn("Interpretation", pdf_text)
        finally:
            chart_pdf.choose_formula = original_choose_formula
            chart_pdf.run_formula = original_run_formula

    def test_sotephwar_voucher_pdf_uses_two_column_card_layout(self):
        original_choose_formula = chart_pdf.choose_formula
        original_run_formula = chart_pdf.run_formula

        chart_pdf.choose_formula = lambda question: "sotephwar_transection_customer"
        chart_pdf.run_formula = lambda formula_name, question: {
            "formula": "sotephwar_transection_customer",
            "period": "this_month",
            "customer": None,
            "unpaid_only": False,
            "invoices": [
                {
                    "invoice_date": "2026-06-01",
                    "invoice_number": "12",
                    "customer_name": "Aye Aye",
                    "item": "Sote Phwar 4L",
                    "quantity": 2,
                    "total_amount": 1000000,
                    "amount_received": 500000,
                    "outstanding_amount": 500000,
                    "note": "Received 2026-06-06",
                },
                {
                    "invoice_date": "2026-06-02",
                    "invoice_number": "13",
                    "customer_name": "Mg Mg",
                    "item": "Sote Phwar 1L",
                    "quantity": 4,
                    "total_amount": 800000,
                    "amount_received": 400000,
                    "outstanding_amount": 400000,
                    "note": "",
                },
            ],
        }
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                output_path = Path(temp_dir) / "vouchers.pdf"

                created = chart_pdf.create_chart_pdf_report("show Sote Phwar vouchers send pdf", output_path)

                self.assertTrue(created)
                pdf_text = output_path.read_bytes().decode("latin-1")
                self.assertIn("Voucher 12", pdf_text)
                self.assertIn("Customer:", pdf_text)
                self.assertIn("Paid", pdf_text)
                self.assertIn("Received:", pdf_text)
                self.assertIn("Outstanding:", pdf_text)
                self.assertIn("1,800,000", pdf_text)
                self.assertIn("900,000", pdf_text)
                self.assertIn("Received 2026-06-06", pdf_text)
        finally:
            chart_pdf.choose_formula = original_choose_formula
            chart_pdf.run_formula = original_run_formula

    def test_sotephwar_voucher_pdf_includes_more_than_twelve_cards(self):
        original_choose_formula = chart_pdf.choose_formula
        original_run_formula = chart_pdf.run_formula

        chart_pdf.choose_formula = lambda question: "sotephwar_transection_customer"
        chart_pdf.run_formula = lambda formula_name, question: {
            "formula": "sotephwar_transection_customer",
            "period": "this_month",
            "customer": "Ma Shwe War",
            "unpaid_only": False,
            "invoices": [
                {
                    "invoice_date": f"2026-06-{day:02d}",
                    "invoice_number": str(day),
                    "customer_name": "Ma Shwe War",
                    "item": "Sote Phwar 1L",
                    "quantity": day,
                    "total_amount": 100000 * day,
                    "amount_received": 0,
                    "outstanding_amount": 100000 * day,
                    "note": "",
                }
                for day in range(1, 14)
            ],
        }
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                output_path = Path(temp_dir) / "vouchers.pdf"

                created = chart_pdf.create_chart_pdf_report("Ma Shwe War vouchers send pdf", output_path)

                self.assertTrue(created)
                pdf_text = output_path.read_bytes().decode("latin-1")
                self.assertIn("Voucher 13", pdf_text)
        finally:
            chart_pdf.choose_formula = original_choose_formula
            chart_pdf.run_formula = original_run_formula

    def test_create_chart_pdf_report_from_structured_result_uses_voucher_cards(self):
        result = {
            "formula": "sotephwar_transection_customer",
            "period": "this_month",
            "customer": "Pwint Aung Kyaw POL",
            "unpaid_only": False,
            "invoices": [
                {
                    "invoice_date": "2026-06-01",
                    "invoice_number": "22",
                    "customer_name": "Pwint Aung Kyaw POL",
                    "item": "Sote Phwar 4L",
                    "quantity": 2,
                    "total_amount": 1000000,
                    "amount_received": 500000,
                    "outstanding_amount": 500000,
                    "note": "Received 2026-06-06",
                },
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "structured-vouchers.pdf"

            created = chart_pdf.create_chart_pdf_report_from_result(
                result,
                "Sote Phwar - Income - Sales By Customer - Pwint Aung Kyaw POL",
                output_path,
            )

            self.assertTrue(created)
            pdf_text = output_path.read_bytes().decode("latin-1")
            self.assertIn("Voucher 22", pdf_text)
            self.assertIn("Customer:", pdf_text)
            self.assertIn("Paid", pdf_text)
            self.assertIn("Received:", pdf_text)
            self.assertIn("Outstanding:", pdf_text)

    def test_sotephwar_voucher_pdf_can_include_two_hundred_cards(self):
        result = {
            "formula": "sotephwar_transection_customer",
            "period": "this_month",
            "customer": "Ma Shwe War",
            "unpaid_only": True,
            "invoices": [
                {
                    "invoice_date": "2026-06-01",
                    "invoice_number": str(index),
                    "customer_name": "Ma Shwe War",
                    "item": "Sote Phwar 4L",
                    "quantity": 1,
                    "total_amount": 100000,
                    "amount_received": 25000,
                    "outstanding_amount": 75000,
                    "note": "",
                }
                for index in range(1, 201)
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "two-hundred-vouchers.pdf"

            created = chart_pdf.create_chart_pdf_report_from_result(
                result,
                "Sote Phwar - Income - Outstanding / Unpaid - Ma Shwe War",
                output_path,
            )

            self.assertTrue(created)
            pdf_text = output_path.read_bytes().decode("latin-1")
            self.assertIn("Voucher 200", pdf_text)

    def test_inventory_stock_pdf_uses_stock_display_layout(self):
        result = {
            "formula": "sotephwar_inventory_stock",
            "period": "this_month",
            "stock": [
                {"store": "Factory", "product": "Sote Phwar 4L", "stock_qty": 25},
                {"store": "Heho Store Home", "product": "Sote Phwar 1L", "stock_qty": 5},
                {"store": "Myit Thar Store", "product": "Sote Phwar 500mL", "stock_qty": 0},
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "stock.pdf"

            created = chart_pdf.create_chart_pdf_report_from_result(
                result,
                "Inventory - Current Stock",
                output_path,
            )

            self.assertTrue(created)
            pdf_text = output_path.read_bytes().decode("latin-1")
            self.assertIn("Stock Summary", pdf_text)
            self.assertIn("Total SKUs", pdf_text)
            self.assertIn("Low Stock", pdf_text)
            self.assertIn("Out of Stock", pdf_text)
            self.assertIn("Sote Phwar 4L", pdf_text)
            self.assertIn("In Stock", pdf_text)

    def test_farm_income_pdf_uses_farm_report_layout(self):
        result = {
            "formula": "category_summary",
            "period": "this_month",
            "_period_label": "This Month",
            "_bi_intent": {
                "business": "farm",
                "module": "income",
                "report": "income_summary",
            },
            "categories": [
                {
                    "sector": "Farm",
                    "category": "Crop Sales",
                    "income": 1250000,
                    "expense": 0,
                    "net": 1250000,
                    "transaction_count": 3,
                },
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "farm-income.pdf"

            created = chart_pdf.create_chart_pdf_report_from_result(
                result,
                "Farm - Income - Income Summary",
                output_path,
            )

            self.assertTrue(created)
            pdf_text = output_path.read_bytes().decode("latin-1")
            self.assertIn("Farm Income Report", pdf_text)
            self.assertIn("Total Farm Income", pdf_text)
            self.assertIn("Income Lines", pdf_text)
            self.assertIn("Crop Sales", pdf_text)
            self.assertIn("This Month", pdf_text)

    def test_farm_expense_pdf_uses_farm_report_layout(self):
        result = {
            "formula": "list_transactions",
            "period": "last_month",
            "_period_label": "Last Month",
            "_bi_intent": {
                "business": "farm",
                "module": "expense",
                "report": "expense_detail",
            },
            "transactions": [
                {
                    "Date": "2026-05-14",
                    "sector": "Farm",
                    "category": "Fertilizer",
                    "item": "NPK fertilizer",
                    "amount": 300000,
                    "payment_method": "Cash",
                },
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "farm-expense.pdf"

            created = chart_pdf.create_chart_pdf_report_from_result(
                result,
                "Farm - Expense - Expense Detail",
                output_path,
            )

            self.assertTrue(created)
            pdf_text = output_path.read_bytes().decode("latin-1")
            self.assertIn("Farm Expense Report", pdf_text)
            self.assertIn("Total Farm Expense", pdf_text)
            self.assertIn("Expense Lines", pdf_text)
            self.assertIn("Fertilizer", pdf_text)
            self.assertIn("NPK fertilizer", pdf_text)

    def test_farm_pdf_wraps_full_category_sentence(self):
        category = "Fertilizer and soil improvement supplies for monsoon paddy field preparation"
        result = {
            "formula": "list_transactions",
            "period": "last_month",
            "_period_label": "Last Month",
            "_bi_intent": {
                "business": "farm",
                "module": "expense",
                "report": "expense_detail",
            },
            "transactions": [
                {
                    "Date": "2026-05-14",
                    "sector": "Farm",
                    "category": category,
                    "item": "Long description for organic compost and basal fertilizer application before transplanting",
                    "amount": 300000,
                    "payment_method": "Cash",
                },
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "farm-expense-long-category.pdf"

            created = chart_pdf.create_chart_pdf_report_from_result(
                result,
                "Farm - Expense - Expense Detail",
                output_path,
            )

            self.assertTrue(created)
            pdf_text = output_path.read_bytes().decode("latin-1")
            self.assertNotIn("...", pdf_text)
            self.assertIn("Fertilizer and soil", pdf_text)
            self.assertIn("monsoon paddy field", pdf_text)
            self.assertIn("preparation", pdf_text)
            self.assertIn("before transplanting", pdf_text)

    def test_sotephwar_transaction_lines_pdf_uses_wrapped_table(self):
        result = {
            "formula": "list_transactions",
            "period": "last_month",
            "_period_label": "Last Month",
            "_bi_intent": {
                "business": "sote_phwar",
                "module": "expense",
                "report": "expense_detail",
            },
            "transactions": [
                {
                    "Date": "2026-05-14",
                    "sector": "Sote Phwar",
                    "category": "Sote Phwar packaging and delivery expense for northern customer route",
                    "item": "Truck delivery fee and carton handling charges for wholesale order",
                    "amount": 300000,
                    "payment_method": "Cash",
                },
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "sotephwar-expense-lines.pdf"

            created = chart_pdf.create_chart_pdf_report_from_result(
                result,
                "Sote Phwar - Expense - Expense Detail",
                output_path,
            )

            self.assertTrue(created)
            pdf_text = output_path.read_bytes().decode("latin-1")
            self.assertIn("Sote Phwar Transaction Lines", pdf_text)
            self.assertIn("Sote Phwar packaging", pdf_text)
            self.assertIn("and delivery expense", pdf_text)
            self.assertIn("for northern customer", pdf_text)
            self.assertIn("route", pdf_text)
            self.assertIn("carton handling", pdf_text)
            self.assertIn("charges for wholesale", pdf_text)
            self.assertNotIn("...", pdf_text)

    def test_bar_chart_long_labels_do_not_overlap_with_ellipsis(self):
        result = {
            "formula": "category_summary",
            "period": "this_month",
            "total_income": 0,
            "total_expense": 1200000,
            "net_total": -1200000,
            "transaction_count": 4,
            "categories": [
                {
                    "sector": "Sote Phwar",
                    "category": "Packaging materials and delivery route expense for wholesale customers",
                    "income": 0,
                    "expense": 1200000,
                    "net": -1200000,
                    "transaction_count": 4,
                },
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "long-label-chart.pdf"

            created = chart_pdf.create_chart_pdf_report_from_result(
                result,
                "Sote Phwar - Expense - Expense Summary",
                output_path,
            )

            self.assertTrue(created)
            pdf_text = output_path.read_bytes().decode("latin-1")
            self.assertIn("Packaging materials and", pdf_text)
            self.assertIn("expense for wholesale", pdf_text)
            self.assertIn("customers", pdf_text)
            self.assertIn("Total", pdf_text)
            self.assertIn("1,200,000", pdf_text)
            self.assertNotIn("...", pdf_text)

    def test_category_summary_text_report_includes_totals(self):
        payload = {
            "title": "Sote Phwar - Expense - Expense Summary",
            "period_label": "This Month",
            "intent": {
                "business": "sote_phwar",
                "module": "expense",
                "report": "expense_summary",
            },
            "result": {
                "formula": "category_summary",
                "total_income": 0,
                "total_expense": 1200000,
                "net_total": -1200000,
                "transaction_count": 4,
                "categories": [
                    {
                        "sector": "Sote Phwar",
                        "category": "Packaging",
                        "income": 0,
                        "expense": 1200000,
                        "net": -1200000,
                        "transaction_count": 4,
                    },
                ],
            },
        }

        report = format_text_report(payload)

        self.assertIn("Total expense: 1,200,000", report)
        self.assertIn("Net total: -1,200,000", report)
        self.assertIn("Rows: 4", report)

    def test_kpi_text_report_includes_unpaid_amount_when_available(self):
        payload = {
            "title": "Sote Phwar - KPI - KPI",
            "period_label": "This Month",
            "intent": {
                "business": "sote_phwar",
                "module": "kpi",
                "report": "kpi",
            },
            "result": {
                "formula": "kpi_overview",
                "total_income": 1000,
                "total_expense": 300,
                "net_profit": 700,
                "profit_margin_percent": 70,
                "amount_received": 800,
                "outstanding_amount": 200,
            },
        }

        report = format_text_report(payload)

        self.assertIn("Received: 800", report)
        self.assertIn("Outstanding / unpaid: 200", report)


if __name__ == "__main__":
    unittest.main()
