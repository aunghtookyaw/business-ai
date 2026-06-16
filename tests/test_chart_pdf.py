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

    def test_sotephwar_voucher_pdf_uses_six_then_eight_cards_per_page(self):
        result = {
            "formula": "sotephwar_transection_customer",
            "period": "this_month",
            "customer": "Ma Shwe War",
            "unpaid_only": False,
            "invoices": [
                {
                    "invoice_date": "2026-06-01",
                    "invoice_number": str(index),
                    "customer_name": "Ma Shwe War",
                    "item": "Sote Phwar 4L",
                    "quantity": 1,
                    "total_amount": 100000,
                    "amount_received": 50000,
                    "outstanding_amount": 50000,
                    "note": "",
                }
                for index in range(1, 15)
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "sotephwar-14-vouchers.pdf"

            created = chart_pdf.create_chart_pdf_report_from_result(
                result,
                "Sote Phwar - Income - Sales By Customer - Ma Shwe War",
                output_path,
            )

            self.assertTrue(created)
            pdf_bytes = output_path.read_bytes()
            pdf_text = pdf_bytes.decode("latin-1")
            self.assertGreaterEqual(pdf_bytes.count(b"/Type /Page "), 1)
            self.assertIn("Voucher 1", pdf_text)
            self.assertIn("Voucher 14", pdf_text)

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

    def test_farm_income_summary_pdf_uses_customer_revenue_report(self):
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
                    "category": "Makro",
                    "customer_name": "Makro",
                    "income": 3000000,
                    "expense": 0,
                    "net": 3000000,
                    "transaction_count": 3,
                    "amount_received": 2500000,
                    "outstanding_amount": 500000,
                },
                {
                    "sector": "Farm",
                    "category": "Bala",
                    "customer_name": "Bala",
                    "income": 1200000,
                    "expense": 0,
                    "net": 1200000,
                    "transaction_count": 3,
                    "amount_received": 1000000,
                    "outstanding_amount": 200000,
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
            self.assertIn("Farm Customer Revenue Report", pdf_text)
            self.assertIn("KPI Summary", pdf_text)
            self.assertIn("Total Sales", pdf_text)
            self.assertIn("Total Paid", pdf_text)
            self.assertIn("Total Outstanding", pdf_text)
            self.assertIn("Top Customers by Revenue", pdf_text)
            self.assertIn("Customer Collection Status", pdf_text)
            self.assertIn("Customer Detail Table", pdf_text)
            self.assertLess(pdf_text.find("Makro"), pdf_text.find("Bala"))

    def test_farm_total_income_pdf_uses_simple_pie_report(self):
        result = {
            "formula": "sales_total",
            "period": "this_year",
            "_bi_intent": {
                "business": "farm",
                "module": "income",
                "report": "total_income",
            },
            "total_sales": 4200,
            "amount_received": 3500,
            "outstanding_amount": 700,
            "transection_income_rows": [
                {
                    "Date": "2026-06-10",
                    "item": "Old item resell",
                    "amount": 900,
                    "payment_method": "Cash",
                },
                {
                    "Date": "2026-06-11",
                    "item": "Misc income",
                    "amount": 400,
                    "payment_method": "Cash",
                },
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "farm-total-income.pdf"

            created = chart_pdf.create_chart_pdf_report_from_result(
                result,
                "Farm - Income - Total Income",
                output_path,
            )

            self.assertTrue(created)
            pdf_text = output_path.read_bytes().decode("latin-1")
            self.assertIn("Farm Total Income", pdf_text)
            self.assertIn("Paid", pdf_text)
            self.assertIn("Outstanding", pdf_text)
            self.assertIn("4,200", pdf_text)
            self.assertIn("Transection Income", pdf_text)
            self.assertIn("Old item resell", pdf_text)
            self.assertNotIn("Top Customers by Revenue", pdf_text)
            self.assertNotIn("Customer Detail Table", pdf_text)

    def test_farm_total_income_text_report_uses_pie_style(self):
        payload = {
            "title": "Farm - Income - Total Income",
            "period_label": "This Year",
            "intent": {
                "business": "farm",
                "module": "income",
                "report": "total_income",
            },
            "result": {
                "formula": "sales_total",
                "total_sales": 4200,
                "amount_received": 3500,
                "outstanding_amount": 700,
                "transection_income_rows": [
                    {
                        "Date": "2026-06-10",
                        "item": "Old item resell",
                        "amount": 900,
                        "payment_method": "Cash",
                    },
                ],
            },
        }

        report = format_text_report(payload)

        self.assertIn("Farm - Income - Total Income", report)
        self.assertIn("Total income: 4,200", report)
        self.assertIn("Paid / received: 3,500", report)
        self.assertIn("Remained: 700", report)
        self.assertIn("Transection Income", report)
        self.assertIn("Old item resell", report)

    def test_sotephwar_income_summary_pdf_uses_customer_revenue_report(self):
        result = {
            "formula": "sotephwar_transection_summary",
            "period": "this_month",
            "invoice_count": 5,
            "total_amount": 4600,
            "amount_received": 2900,
            "outstanding_amount": 1700,
            "customers": [
                {
                    "customer_name": "Bala",
                    "total_amount": 1200,
                    "amount_received": 500,
                    "outstanding_amount": 700,
                },
                {
                    "customer_name": "Makro",
                    "total_amount": 3000,
                    "amount_received": 2200,
                    "outstanding_amount": 800,
                },
                {
                    "customer_name": "Aye",
                    "total_amount": 400,
                    "amount_received": 200,
                    "outstanding_amount": 200,
                },
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "sotephwar-income-summary.pdf"

            created = chart_pdf.create_chart_pdf_report_from_result(
                result,
                "Sote Phwar - Income - Income Summary",
                output_path,
            )

            self.assertTrue(created)
            pdf_text = output_path.read_bytes().decode("latin-1")
            self.assertIn("Customer Revenue Report", pdf_text)
            self.assertIn("KPI Summary", pdf_text)
            self.assertIn("Total Sales", pdf_text)
            self.assertIn("Total Paid", pdf_text)
            self.assertIn("Total Outstanding", pdf_text)
            self.assertIn("Top Customers by Revenue", pdf_text)
            self.assertIn("Customer Collection Status", pdf_text)
            self.assertIn("Customer Detail Table", pdf_text)
            self.assertNotIn("Paid vs Outstanding", pdf_text)
            self.assertLess(pdf_text.find("Makro"), pdf_text.find("Bala"))
            self.assertLess(pdf_text.find("Bala"), pdf_text.find("Aye"))

    def test_sotephwar_total_income_pdf_uses_simple_paid_outstanding_pie(self):
        result = {
            "formula": "sotephwar_transection_summary",
            "period": "this_year",
            "_bi_intent": {
                "business": "sote_phwar",
                "module": "income",
                "report": "total_income",
            },
            "invoice_count": 3,
            "total_amount": 4600,
            "amount_received": 2900,
            "outstanding_amount": 1700,
            "customers": [
                {
                    "customer_name": "Makro",
                    "total_amount": 3000,
                    "amount_received": 2200,
                    "outstanding_amount": 800,
                },
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "sotephwar-total-income.pdf"

            created = chart_pdf.create_chart_pdf_report_from_result(
                result,
                "Sote Phwar - Income - Total Income",
                output_path,
            )

            self.assertTrue(created)
            pdf_text = output_path.read_bytes().decode("latin-1")
            self.assertIn("Sote Phwar Total Income", pdf_text)
            self.assertIn("Paid", pdf_text)
            self.assertIn("Outstanding", pdf_text)
            self.assertIn("4,600", pdf_text)
            self.assertNotIn("Top Customers by Revenue", pdf_text)
            self.assertNotIn("Customer Detail Table", pdf_text)

    def test_sotephwar_income_summary_pdf_continues_revenue_bars_across_pages(self):
        customers = [
            {
                "customer_name": f"Customer {index:02d}",
                "total_amount": 100000 - index,
                "amount_received": 50000,
                "outstanding_amount": 50000 - index,
            }
            for index in range(1, 41)
        ]
        result = {
            "formula": "sotephwar_transection_summary",
            "period": "this_year",
            "invoice_count": 40,
            "total_amount": sum(row["total_amount"] for row in customers),
            "amount_received": sum(row["amount_received"] for row in customers),
            "outstanding_amount": sum(row["outstanding_amount"] for row in customers),
            "customers": customers,
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "sotephwar-income-summary-pages.pdf"

            created = chart_pdf.create_chart_pdf_report_from_result(
                result,
                "Sote Phwar - Income - Income Summary",
                output_path,
            )

            self.assertTrue(created)
            pdf_text = output_path.read_bytes().decode("latin-1")
            self.assertIn("Top Customers by Revenue", pdf_text)
            self.assertIn("Top Customers by Revenue \\(continued\\)", pdf_text)
            self.assertIn("Customer 40", pdf_text)
            self.assertLess(pdf_text.find("Customer 40"), pdf_text.find("Customer Detail Table"))

    def test_farm_sales_by_customer_pdf_uses_income_cards(self):
        result = {
            "formula": "farm_transection_customer",
            "period": "this_month",
            "_period_label": "This Month",
            "_bi_intent": {
                "business": "farm",
                "module": "income",
                "report": "sales_by_customer",
                "customer": "Makro",
            },
            "total_sales": 20624200,
            "amount_received": 20624200,
            "outstanding_amount": 0,
            "invoice_count": 1,
            "invoices": [
                {
                    "invoice_date": "2026-06-15",
                    "invoice_number": "12",
                    "customer_name": "Makro",
                    "item": "Farm Sales",
                    "total_amount": 20624200,
                    "amount_received": 20624200,
                    "outstanding_amount": 0,
                    "note": "Paid by K Pay",
                },
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "farm-makro-sales.pdf"

            created = chart_pdf.create_chart_pdf_report_from_result(
                result,
                "Farm - Income - Sales By Customer - Makro",
                output_path,
            )

            self.assertTrue(created)
            pdf_text = output_path.read_bytes().decode("latin-1")
            self.assertIn("Farm Income Report", pdf_text)
            self.assertIn("Income Lines", pdf_text)
            self.assertIn("Voucher 12", pdf_text)
            self.assertIn("2026-06-15", pdf_text)
            self.assertIn("Makro", pdf_text)
            self.assertIn("Received:", pdf_text)
            self.assertIn("Outstanding:", pdf_text)
            self.assertIn("Paid by K Pay", pdf_text)
            self.assertIn("20,624,200", pdf_text)

    def test_farm_income_pdf_uses_six_then_eight_cards_per_page(self):
        result = {
            "formula": "farm_transection_customer",
            "period": "this_month",
            "_period_label": "This Month",
            "_bi_intent": {
                "business": "farm",
                "module": "income",
                "report": "sales_by_customer",
                "customer": "Makro",
            },
            "total_sales": 1400000,
            "amount_received": 1400000,
            "outstanding_amount": 0,
            "invoice_count": 14,
            "invoices": [
                {
                    "invoice_date": "2026-06-01",
                    "invoice_number": str(index),
                    "customer_name": "Makro",
                    "item": "Farm Sales",
                    "total_amount": 100000,
                    "amount_received": 100000,
                    "outstanding_amount": 0,
                    "note": "",
                }
                for index in range(1, 15)
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "farm-14-vouchers.pdf"

            created = chart_pdf.create_chart_pdf_report_from_result(
                result,
                "Farm - Income - Sales By Customer - Makro",
                output_path,
            )

            self.assertTrue(created)
            pdf_bytes = output_path.read_bytes()
            pdf_text = pdf_bytes.decode("latin-1")
            self.assertEqual(2, pdf_bytes.count(b"/Type /Page "))
            self.assertIn("Voucher 1", pdf_text)
            self.assertIn("Voucher 14", pdf_text)

    def test_farm_expense_pdf_uses_standard_detail_layout(self):
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
            self.assertIn("Expense Detail", pdf_text)
            self.assertIn("Data Table", pdf_text)
            self.assertIn("Fertilizer", pdf_text)
            self.assertIn("NPK fertilizer", pdf_text)

    def test_expense_detail_pdf_uses_standard_chart_table_layout(self):
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
            output_path = Path(temp_dir) / "expense-detail-standard.pdf"

            created = chart_pdf.create_chart_pdf_report_from_result(
                result,
                "Farm - Expense - Expense Detail",
                output_path,
            )

            self.assertTrue(created)
            pdf_text = output_path.read_bytes().decode("latin-1")
            self.assertIn("Expense Detail", pdf_text)
            self.assertIn("Data Table", pdf_text)
            self.assertIn("NPK fertilizer", pdf_text)
            self.assertNotIn("Farm Expense Report", pdf_text)

    def test_income_by_category_and_detail_pdf_use_standard_layout(self):
        category_result = {
            "formula": "category_summary",
            "period": "this_month",
            "_period_label": "This Month",
            "_bi_intent": {
                "business": "farm",
                "module": "income",
                "report": "income_by_category",
            },
            "total_income": 500000,
            "total_expense": 0,
            "net_total": 500000,
            "transaction_count": 2,
            "categories": [
                {
                    "sector": "Farm",
                    "category": "Vegetable Sales",
                    "income": 500000,
                    "expense": 0,
                    "net": 500000,
                    "transaction_count": 2,
                },
            ],
        }
        detail_result = {
            "formula": "list_transactions",
            "period": "this_month",
            "_period_label": "This Month",
            "_bi_intent": {
                "business": "farm",
                "module": "income",
                "report": "income_detail",
            },
            "transactions": [
                {
                    "Date": "2026-06-01",
                    "sector": "Farm",
                    "category": "Vegetable Sales",
                    "item": "General income filling",
                    "amount": 500000,
                    "payment_method": "K Pay",
                },
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            category_path = Path(temp_dir) / "income-category.pdf"
            detail_path = Path(temp_dir) / "income-detail.pdf"

            self.assertTrue(chart_pdf.create_chart_pdf_report_from_result(
                category_result,
                "Farm - Income - Income By Category",
                category_path,
            ))
            self.assertTrue(chart_pdf.create_chart_pdf_report_from_result(
                detail_result,
                "Farm - Income - Income Detail",
                detail_path,
            ))

            category_text = category_path.read_bytes().decode("latin-1")
            detail_text = detail_path.read_bytes().decode("latin-1")
            self.assertIn("Income by Category", category_text)
            self.assertIn("Data Table", category_text)
            self.assertIn("Income Detail", detail_text)
            self.assertIn("Data Table", detail_text)
            self.assertIn("General income filling", detail_text)
            self.assertIn("Vegetable Sales", detail_text)
            self.assertNotIn("Voucher Number", detail_text)
            self.assertNotIn("Farm Income Report", detail_text)

    def test_unicode_voucher_pdf_does_not_use_ascii_question_marks(self):
        customer = "မောင်မောင်"
        result = {
            "formula": "sotephwar_transection_customer",
            "period": "this_month",
            "customer": customer,
            "invoices": [
                {
                    "invoice_date": "2026-06-01",
                    "invoice_number": "12",
                    "customer_name": customer,
                    "item": "ဆီ",
                    "quantity": 1,
                    "total_amount": 100000,
                    "amount_received": 50000,
                    "outstanding_amount": 50000,
                    "note": "မှတ်ချက်",
                },
            ],
        }
        spec = chart_pdf._chart_spec(result, "Sote Phwar - Income")
        lines = chart_pdf._unicode_pdf_lines("Unicode Test", "မြန်မာ voucher", spec)

        self.assertIn(customer, "\n".join(lines))
        self.assertNotIn("????", "\n".join(lines))
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "unicode-voucher.pdf"

            created = chart_pdf.create_chart_pdf_report_from_result(
                result,
                "မြန်မာ voucher",
                output_path,
                title="Unicode Test",
            )

            self.assertTrue(created)
            self.assertTrue(output_path.read_bytes().startswith(b"%PDF"))

    def test_unicode_sotephwar_income_detail_uses_standard_detail_table(self):
        item = "အထွေထွေ ဝင်ငွေ"
        result = {
            "formula": "list_transactions",
            "period": "this_month",
            "_bi_intent": {
                "business": "sote_phwar",
                "module": "income",
                "report": "income_detail",
            },
            "transactions": [
                {
                    "Date": "2026-06-01",
                    "sector": "Sote Phwar",
                    "category": "General Income",
                    "item": item,
                    "amount": 100000,
                    "payment_method": "Cash",
                },
            ],
        }
        spec = chart_pdf._chart_spec(result, "Sote Phwar - Income Detail")
        lines = chart_pdf._unicode_pdf_lines("Unicode Test", "မြန်မာ income detail", spec)
        joined = "\n".join(lines)

        self.assertEqual("bar", spec["kind"])
        self.assertIn("Date | Item | Sector | Category | Payment | Amount", joined)
        self.assertIn(item, joined)
        self.assertNotIn("????", joined)

    def test_unicode_farm_income_detail_uses_voucher_table(self):
        customer = "ဒေါ်အေး"
        result = {
            "formula": "farm_transection_customer",
            "period": "this_month",
            "_bi_intent": {
                "business": "farm",
                "module": "income",
                "report": "income_detail",
            },
            "invoices": [
                {
                    "invoice_date": "2026-06-02",
                    "invoice_number": "F-7",
                    "customer_name": customer,
                    "total_amount": 200000,
                    "amount_received": 125000,
                    "outstanding_amount": 75000,
                },
            ],
        }
        spec = chart_pdf._chart_spec(result, "Farm - Income Detail")
        lines = chart_pdf._unicode_pdf_lines("Unicode Test", "မြန်မာ farm income detail", spec)
        joined = "\n".join(lines)

        self.assertEqual("voucher_table", spec["kind"])
        self.assertIn("Voucher Number | Date | Customer | Total | Paid | Outstanding", joined)
        self.assertIn(customer, joined)
        self.assertIn("Total: 200,000 | Paid: 125,000 | Outstanding: 75,000", joined)
        self.assertNotIn("????", joined)

    def test_unicode_farm_expense_detail_pdf_uses_unicode_fallback(self):
        category = "မြေသြဇာ"
        result = {
            "formula": "list_transactions",
            "period": "this_month",
            "_period_label": "This Month",
            "_bi_intent": {
                "business": "farm",
                "module": "expense",
                "report": "expense_detail",
            },
            "transactions": [
                {
                    "Date": "2026-06-01",
                    "sector": "Farm",
                    "category": category,
                    "item": "စိုက်ပျိုးရေး သုံးစွဲမှု",
                    "amount": 100000,
                    "payment_method": "Cash",
                },
            ],
        }
        spec = chart_pdf._chart_spec(result, "Farm - Expense")
        lines = chart_pdf._unicode_pdf_lines("Unicode Test", "Farm - Expense", spec)

        self.assertIn(category, "\n".join(lines))
        self.assertNotIn("????", "\n".join(lines))
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "unicode-farm-expense.pdf"

            created = chart_pdf.create_chart_pdf_report_from_result(
                result,
                "Farm - Expense",
                output_path,
                title="Unicode Test",
            )

            self.assertTrue(created)
            self.assertTrue(output_path.read_bytes().startswith(b"%PDF"))

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
            self.assertIn("Fertilizer and", pdf_text)
            self.assertIn("soil improvement", pdf_text)
            self.assertIn("monsoon paddy", pdf_text)
            self.assertIn("preparation", pdf_text)
            self.assertIn("before", pdf_text)
            self.assertIn("transplanting", pdf_text)

    def test_sotephwar_transaction_lines_pdf_uses_standard_detail_layout(self):
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
            self.assertIn("Expense Detail", pdf_text)
            self.assertIn("Data Table", pdf_text)
            self.assertIn("Sote Phwar", pdf_text)
            self.assertIn("packaging and", pdf_text)
            self.assertIn("delivery expense", pdf_text)
            self.assertIn("for northern", pdf_text)
            self.assertIn("customer route", pdf_text)
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

    def test_sotephwar_income_summary_text_report_uses_customer_revenue_style(self):
        payload = {
            "title": "Sote Phwar - Income - Income Summary",
            "period_label": "This Month",
            "intent": {
                "business": "sote_phwar",
                "module": "income",
                "report": "income_summary",
            },
            "result": {
                "formula": "sotephwar_transection_summary",
                "invoice_count": 3,
                "total_amount": 4600,
                "amount_received": 2900,
                "outstanding_amount": 1700,
                "customers": [
                    {
                        "customer_name": "Bala",
                        "total_amount": 1200,
                        "amount_received": 500,
                        "outstanding_amount": 700,
                    },
                    {
                        "customer_name": "Makro",
                        "total_amount": 3000,
                        "amount_received": 2200,
                        "outstanding_amount": 800,
                    },
                ],
            },
        }

        report = format_text_report(payload)

        self.assertIn("KPI Summary", report)
        self.assertIn("Total Sales: 4,600", report)
        self.assertIn("Total Paid: 2,900", report)
        self.assertIn("Total Outstanding: 1,700", report)
        self.assertIn("Top Customers by Revenue", report)
        self.assertIn("Customer Collection Status", report)
        self.assertLess(report.find("Makro"), report.find("Bala"))
        self.assertNotIn("Invoices:", report)

    def test_farm_income_summary_text_report_uses_customer_revenue_style(self):
        payload = {
            "title": "Farm - Income - Income Summary",
            "period_label": "This Month",
            "intent": {
                "business": "farm",
                "module": "income",
                "report": "income_summary",
            },
            "result": {
                "formula": "category_summary",
                "total_income": 4200,
                "total_expense": 0,
                "net_total": 4200,
                "transaction_count": 6,
                "categories": [
                    {
                        "sector": "Farm",
                        "category": "Bala",
                        "customer_name": "Bala",
                        "income": 1200,
                        "expense": 0,
                        "net": 1200,
                        "transaction_count": 3,
                        "amount_received": 1000,
                        "outstanding_amount": 200,
                    },
                    {
                        "sector": "Farm",
                        "category": "Makro",
                        "customer_name": "Makro",
                        "income": 3000,
                        "expense": 0,
                        "net": 3000,
                        "transaction_count": 3,
                        "amount_received": 2500,
                        "outstanding_amount": 500,
                    },
                ],
            },
        }

        report = format_text_report(payload)

        self.assertIn("KPI Summary", report)
        self.assertIn("Total Sales: 4,200", report)
        self.assertIn("Total Paid: 3,500", report)
        self.assertIn("Total Outstanding: 700", report)
        self.assertIn("Top Customers by Revenue", report)
        self.assertIn("Customer Collection Status", report)
        self.assertLess(report.find("Makro"), report.find("Bala"))
        self.assertNotIn("Category summary", report)

    def test_financial_obligation_due_text_report_includes_action_fields(self):
        payload = {
            "title": "Financial Obligation - Financial Obligation - Due Soon",
            "period_label": "This Month",
            "intent": {
                "business": "financial_obligation",
                "module": "financial_obligation",
                "report": "financial_obligation_due",
            },
            "result": {
                "formula": "financial_obligation_due",
                "days": 30,
                "obligations": [
                    {
                        "next_due_date": "2026-06-30",
                        "creditor": "U Aung",
                        "category": "Loan",
                        "subcategory": "Investor Loan",
                        "frequency": "Monthly",
                        "status": "Active",
                        "amount": 500000,
                        "days_until_due": 15,
                        "notes": "Call before payment",
                    },
                ],
            },
        }

        report = format_text_report(payload)

        self.assertIn("next_due_date: 2026-06-30", report)
        self.assertIn("creditor: U Aung", report)
        self.assertIn("amount: 500,000", report)
        self.assertIn("status: Active", report)
        self.assertIn("notes: Call before payment", report)

    def test_income_detail_text_report_uses_fixed_width_columns(self):
        payload = {
            "title": "Farm - Income - Income Detail",
            "period_label": "This Month",
            "intent": {
                "business": "farm",
                "module": "income",
                "report": "income_detail",
            },
            "result": {
                "formula": "list_transactions",
                "period": "this_month",
                "transactions": [
                    {
                        "Date": "2026-06-01",
                        "sector": "Farm",
                        "category": "Very Long Income Category That Must Not Shift",
                        "item": "General income filling description that is long",
                        "amount": 500000,
                        "payment_method": "K Pay",
                    },
                    {
                        "Date": "2026-06-02",
                        "sector": "Farm",
                        "category": "Sales",
                        "item": "Short",
                        "amount": 50,
                        "payment_method": "Cash",
                    },
                ],
            },
        }

        report = format_text_report(payload)
        lines = report.splitlines()
        header = next(line for line in lines if line.startswith("Date"))
        separator = lines[lines.index(header) + 1]
        rows = lines[lines.index(header) + 2:lines.index(header) + 4]
        expected_width = 10 + 1 + 25 + 1 + 12 + 1 + 25 + 1 + 12 + 1 + 15

        self.assertEqual(expected_width, len(header))
        self.assertEqual(expected_width, len(separator))
        self.assertTrue(all(len(row) == expected_width for row in rows))
        self.assertEqual("2026-06-01", rows[0][:10])
        self.assertEqual("General income filling de", rows[0][11:36])
        self.assertEqual("Farm        ", rows[0][37:49])
        self.assertEqual("Very Long Income Category", rows[0][50:75])
        self.assertEqual("K Pay       ", rows[0][76:88])
        self.assertEqual("        500,000", rows[0][89:104])
        self.assertEqual("Short                    ", rows[1][11:36])
        self.assertEqual("             50", rows[1][89:104])

if __name__ == "__main__":
    unittest.main()
