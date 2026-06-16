import math
import re
import subprocess
import tempfile
import textwrap
from datetime import datetime
from pathlib import Path

from business_agent import FAST_FORMULAS, choose_formula
from tools.formula_engine import run_formula


PALETTE = [
    (47, 128, 237),
    (39, 174, 96),
    (242, 153, 74),
    (235, 87, 87),
    (155, 81, 224),
    (86, 204, 242),
    (111, 207, 151),
    (242, 201, 76),
]


def _ascii(text):
    return "".join(char if 32 <= ord(char) < 127 else "?" for char in str(text))


def _contains_non_ascii(value):
    if isinstance(value, str):
        return any(ord(char) > 127 for char in value)
    if isinstance(value, dict):
        return any(_contains_non_ascii(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(_contains_non_ascii(item) for item in value)
    return False


def _escape_pdf_text(text):
    return _ascii(text).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _money(value):
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return str(value)


def _unicode_value(value):
    if value in (None, ""):
        return "-"
    if isinstance(value, (int, float)):
        return _money(value)
    return str(value)


def _short_label(value, length=28):
    label = " ".join(_ascii(value).split())
    if len(label) <= length:
        return label
    return label[:length - 3].rstrip() + "..."


def _wrap_pdf_text(value, width, size):
    chars = max(8, int(width / (size * 0.52)))
    return textwrap.wrap(" ".join(_ascii(value).split()) or "-", width=chars) or ["-"]


def _percentile(values, percent):
    if not values:
        return 0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percent
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[int(position)]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


class PdfCanvas:
    def __init__(self, title):
        self.title = title
        self.pages = []
        self.width = 595
        self.height = 842
        self._content = []

    def new_page(self):
        if self._content:
            self.pages.append("\n".join(self._content).encode("latin-1"))
        self._content = []

    def finish(self, output_path):
        if self._content:
            self.pages.append("\n".join(self._content).encode("latin-1"))
            self._content = []
        if not self.pages:
            self.pages.append(b"")

        objects = [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            None,
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
        ]
        page_ids = []
        for page in self.pages:
            page_id = len(objects) + 1
            content_id = len(objects) + 2
            page_ids.append(page_id)
            objects.append(
                (
                    f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {self.width} {self.height}] "
                    f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {content_id} 0 R >>"
                ).encode("latin-1")
            )
            objects.append(
                b"<< /Length " + str(len(page)).encode("latin-1") + b" >>\nstream\n" + page + b"\nendstream"
            )

        kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
        objects[1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode("latin-1")

        output = bytearray(b"%PDF-1.4\n")
        offsets = [0]
        for index, obj in enumerate(objects, start=1):
            offsets.append(len(output))
            output.extend(f"{index} 0 obj\n".encode("latin-1"))
            output.extend(obj)
            output.extend(b"\nendobj\n")
        xref_offset = len(output)
        output.extend(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
        output.extend(b"0000000000 65535 f \n")
        for offset in offsets[1:]:
            output.extend(f"{offset:010d} 00000 n \n".encode("latin-1"))
        output.extend(
            (
                f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
                f"startxref\n{xref_offset}\n%%EOF\n"
            ).encode("latin-1")
        )
        Path(output_path).write_bytes(output)

    def color(self, rgb):
        r, g, b = [component / 255 for component in rgb]
        self._content.append(f"{r:.3f} {g:.3f} {b:.3f} rg {r:.3f} {g:.3f} {b:.3f} RG")

    def stroke_color(self, rgb):
        r, g, b = [component / 255 for component in rgb]
        self._content.append(f"{r:.3f} {g:.3f} {b:.3f} RG")

    def line_width(self, width):
        self._content.append(f"{width:.2f} w")

    def text(self, x, y, text, size=10, bold=False, max_width=None, color=(17, 24, 39)):
        font = "F2" if bold else "F1"
        lines = [str(text)]
        if max_width:
            chars = max(8, int(max_width / (size * 0.52)))
            lines = textwrap.wrap(str(text), width=chars) or [""]
        r, g, b = [component / 255 for component in color]
        self._content.append(f"{r:.3f} {g:.3f} {b:.3f} rg")
        for index, line in enumerate(lines):
            yy = y - (index * (size + 3))
            self._content.append(f"BT /{font} {size} Tf {x:.2f} {yy:.2f} Td ({_escape_pdf_text(line)}) Tj ET")
        return len(lines) * (size + 3)

    def rect(self, x, y, width, height, fill=None, stroke=None):
        if fill:
            self.color(fill)
            self._content.append(f"{x:.2f} {y:.2f} {width:.2f} {height:.2f} re f")
        if stroke:
            self.stroke_color(stroke)
            self._content.append(f"{x:.2f} {y:.2f} {width:.2f} {height:.2f} re S")

    def line(self, x1, y1, x2, y2, color=(60, 60, 60), width=1):
        self.stroke_color(color)
        self.line_width(width)
        self._content.append(f"{x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S")

    def polygon(self, points, fill):
        if not points:
            return
        self.color(fill)
        first = points[0]
        commands = [f"{first[0]:.2f} {first[1]:.2f} m"]
        commands.extend(f"{x:.2f} {y:.2f} l" for x, y in points[1:])
        commands.append("h f")
        self._content.append(" ".join(commands))


def _forced_chart_type(question):
    text = question.lower()
    if "box" in text or "whisker" in text:
        return "box"
    if "pie" in text:
        return "pie"
    if "stack" in text:
        return "stacked_bar"
    if "table" in text:
        return "table"
    if "bar" in text:
        return "bar"
    return None


def _chart_spec(result, question):
    formula = result.get("formula")
    forced = _forced_chart_type(question)
    bi_intent = result.get("_bi_intent") or {}
    report = bi_intent.get("report") or ""

    if (
        bi_intent.get("business") == "farm"
        and bi_intent.get("module") in {"income", "expense"}
        and report not in {
            "expense_by_category",
            "expense_detail",
            "income_by_category",
            "income_detail",
            "income_transactions",
        }
        and not forced
    ):
        return _farm_financial_spec(result, question, bi_intent)

    if formula in ("kpi_overview", "gross_profit"):
        values = [
            ("Income", result.get("total_income", result.get("income", 0))),
            ("Expense", result.get("total_expense", result.get("expense", 0))),
        ]
        return {
            "kind": forced or "pie",
            "title": "Income vs Expense",
            "reason": "Best method: pie chart shows the income and expense share quickly; bar chart is useful when comparing exact amounts.",
            "values": values,
            "table": [("Metric", "Amount")] + values + [("Profit", result.get("net_profit", result.get("gross_profit", 0)))],
        }

    if formula == "cash_flow":
        rows = result.get("by_payment_method") or []
        return {
            "kind": forced or "stacked_bar",
            "title": "Cash Flow by Payment Method",
            "reason": "Best method: stacked bar compares inflow and outflow by payment method while keeping the net cash position visible.",
            "series": [("Inflow", "inflow"), ("Outflow", "outflow")],
            "rows": rows,
            "label_key": "payment_method",
            "table": [("Payment", "Inflow", "Outflow", "Net")] + [
                (row["payment_method"], row["inflow"], row["outflow"], row["net_cash_flow"]) for row in rows
            ],
        }

    if formula == "sector_summary":
        rows = result.get("sectors") or []
        return {
            "kind": forced or "stacked_bar",
            "title": "Sector Income and Expense",
            "reason": "Best method: stacked bar compares income and expense side by side for each sector.",
            "series": [("Income", "income"), ("Expense", "expense")],
            "rows": rows,
            "label_key": "sector",
            "table": [("Sector", "Income", "Expense", "Profit")] + [
                (row["sector"], row["income"], row["expense"], row["profit"]) for row in rows
            ],
        }

    if formula == "category_summary":
        rows = (result.get("categories") or [])[:12]
        total_income = result.get("total_income", sum(row.get("income", 0) for row in result.get("categories") or []))
        total_expense = result.get("total_expense", sum(row.get("expense", 0) for row in result.get("categories") or []))
        net_total = result.get("net_total", total_income - total_expense)
        transaction_count = result.get("transaction_count", sum(row.get("transaction_count", 0) for row in result.get("categories") or []))
        module = bi_intent.get("module") or ""
        amount_key = "income" if module == "income" else "expense"
        title = "Income by Category" if module == "income" else "Expense by Category"
        if report in {"income_summary", "expense_summary"}:
            title = "Income Summary" if module == "income" else "Expense Summary"
        return {
            "kind": forced or "bar",
            "title": title,
            "reason": "Best method: bar chart ranks categories, which is clearer than pie when there are many categories.",
            "total_income": total_income,
            "total_expense": total_expense,
            "net_total": net_total,
            "transaction_count": transaction_count,
            "values": [(f"{row['sector']} / {row['category']}", row.get(amount_key) or abs(row.get("net", 0))) for row in rows],
            "table": [("Category", "Income", "Expense", "Net", "Rows")] + [
                (f"{row['sector']} / {row['category']}", row["income"], row["expense"], row["net"], row["transaction_count"]) for row in rows
            ] + [("Total", total_income, total_expense, net_total, transaction_count)],
        }

    if formula in ("top_expenses", "top_income"):
        key = "expenses" if formula == "top_expenses" else "income"
        rows = result.get(key) or []
        return {
            "kind": forced or "bar",
            "title": "Top Expenses" if key == "expenses" else "Top Income",
            "reason": "Best method: bar chart is the clearest way to rank top records by amount.",
            "values": [(row.get("item") or row.get("category") or row.get("Date"), row.get("amount", 0)) for row in rows],
            "table": [("Date", "Item", "Sector", "Category", "Amount")] + [
                (row.get("Date"), row.get("item"), row.get("sector"), row.get("category"), row.get("amount")) for row in rows
            ],
        }

    if formula == "sotephwar_transection_customer":
        rows = result.get("invoices") or []
        return {
            "kind": forced or "voucher_cards",
            "title": "Sote Phwar Vouchers",
            "reason": "Best method: two-column voucher cards keep customer, voucher number, paid amount, outstanding amount, and notes readable.",
            "vouchers": rows,
            "table": [("Voucher", "Customer", "Total", "Paid", "Outstanding")] + [
                (
                    row.get("invoice_number"),
                    row.get("customer_name"),
                    row.get("total_amount", 0),
                    row.get("amount_received", 0),
                    row.get("outstanding_amount", 0),
                )
                for row in rows
            ],
        }

    if formula in ("list_transactions", "sotephwar_transection_list"):
        rows = result.get("transactions") or result.get("invoices") or []
        amount_key = "amount" if result.get("transactions") else "total_amount"
        values = [int(row.get(amount_key) or 0) for row in rows]
        if report in {"expense_detail", "income_detail", "income_transactions"}:
            is_income = bi_intent.get("module") == "income"
            return {
                "kind": forced or "bar",
                "title": "Income Detail" if is_income else "Expense Detail",
                "reason": "Best method: bar chart ranks transaction lines by amount, with the table below for exact review.",
                "values": [
                    (
                        row.get("item") or row.get("category") or row.get("Date") or row.get("invoice_date"),
                        row.get(amount_key, 0),
                    )
                    for row in rows[:12]
                ],
                "table": [("Date", "Item", "Sector", "Category", "Payment", "Amount")] + [
                    (
                        row.get("Date") or row.get("invoice_date"),
                        row.get("item") or row.get("customer_name") or "-",
                        row.get("sector") or "-",
                        row.get("category") or "-",
                        row.get("payment_method") or "-",
                        row.get(amount_key, 0),
                    )
                    for row in rows[:30]
                ],
            }
        if bi_intent.get("business") == "sote_phwar" and bi_intent.get("module") in {"income", "expense"}:
            return {
                "kind": forced or "table",
                "title": "Sote Phwar Transaction Lines",
                "reason": "Best method: table format keeps date, category, description, payment method, and amount readable.",
                "values": [(row.get("category") or row.get("item") or row.get("Date"), row.get(amount_key, 0)) for row in rows],
                "table": [("Date", "Category", "Description", "Payment", "Amount")] + [
                    (
                        row.get("Date") or row.get("invoice_date"),
                        row.get("category") or "-",
                        row.get("item") or row.get("customer_name") or "-",
                        row.get("payment_method") or "-",
                        row.get(amount_key, 0),
                    )
                    for row in rows[:30]
                ],
            }
        table = [("Date", "Name/Item", "Amount", "Received", "Outstanding")]
        for row in rows[:20]:
            table.append((
                row.get("Date") or row.get("invoice_date"),
                row.get("customer_name") or row.get("item"),
                row.get(amount_key, 0),
                row.get("amount_received", "-"),
                row.get("outstanding_amount", "-"),
            ))
        return {
            "kind": forced or ("box" if len(values) >= 5 else "table"),
            "title": "Transaction Amount Distribution",
            "reason": "Best method: box and whisker plot shows spread and outliers when there are enough transaction rows; table is best for exact row review.",
            "values": values,
            "table": table,
        }

    if formula == "sotephwar_transection_summary":
        values = [
            ("Received", result.get("amount_received", 0)),
            ("Outstanding", result.get("outstanding_amount", 0)),
        ]
        return {
            "kind": forced or "pie",
            "title": "Sote Phwar Received vs Outstanding",
            "reason": "Best method: pie chart highlights how much of total invoice value is collected versus still outstanding.",
            "values": values,
            "table": [("Metric", "Amount"), ("Total", result.get("total_amount", 0))] + values,
        }

    if formula in ("sotephwar_transection_top", "sotephwar_transection_quantity"):
        rows = result.get("invoices") or [result]
        return {
            "kind": forced or "bar",
            "title": "Sote Phwar Invoice Amounts",
            "reason": "Best method: bar chart ranks invoice or item amounts for quick comparison.",
            "values": [(row.get("customer_name") or row.get("item"), row.get("total_amount", 0)) for row in rows],
            "table": [("Customer/Item", "Quantity", "Total", "Received", "Outstanding")] + [
                (row.get("customer_name") or row.get("item"), row.get("quantity", 0), row.get("total_amount", 0), row.get("amount_received", 0), row.get("outstanding_amount", 0)) for row in rows
            ],
        }

    if formula == "sotephwar_inventory_stock":
        rows = result.get("stock") or []
        return {
            "kind": forced or "stock_sheet",
            "title": "Sote Phwar Inventory Stock",
            "reason": "Best method: stock sheet format shows SKU counts, low/out stock status, and current quantities in an inventory-style display.",
            "stock": rows,
            "values": [(f"{row['store']} / {row['product']}", row["stock_qty"]) for row in rows],
            "table": [("Store", "Product", "Stock")] + [(row["store"], row["product"], row["stock_qty"]) for row in rows],
        }

    if formula == "sotephwar_inventory_movement_summary":
        rows = result.get("movements") or []
        return {
            "kind": forced or "bar",
            "title": "Inventory Movement Quantity",
            "reason": "Best method: bar chart compares movement quantities by type and product.",
            "values": [(f"{row['type']} / {row['product']}", row["quantity"]) for row in rows],
            "table": [("Type", "Product", "Quantity", "Rows")] + [(row["type"], row["product"], row["quantity"], row["movement_count"]) for row in rows],
        }

    if formula == "financial_obligation_summary":
        rows = result.get("summary") or []
        return {
            "kind": forced or "bar",
            "title": "Financial Obligations",
            "reason": "Best method: bar chart ranks obligation amounts by category and status.",
            "values": [(f"{row['category']} / {row['status']}", row["amount"]) for row in rows],
            "table": [("Category/Status", "Amount", "Rows", "Next Due")] + [
                (f"{row['category']} / {row['status']}", row["amount"], row["obligation_count"], row["next_due_date"]) for row in rows
            ],
        }

    if formula in ("financial_obligation_due", "financial_obligation_list"):
        rows = result.get("obligations") or []
        title = "Financial Obligations Due Soon" if formula == "financial_obligation_due" else "Financial Obligation List"
        return {
            "kind": forced or "table",
            "title": title,
            "reason": "Best method: table format keeps creditor, due date, status, frequency, and amount readable.",
            "values": [(row.get("creditor") or row.get("category") or row.get("id"), row.get("amount", 0)) for row in rows],
            "table": [("Due Date", "Creditor", "Category", "Status", "Amount")] + [
                (
                    row.get("next_due_date"),
                    row.get("creditor"),
                    row.get("category"),
                    row.get("status"),
                    row.get("amount", 0),
                )
                for row in rows
            ],
        }

    return None


def _farm_financial_spec(result, question, intent):
    module = intent.get("module")
    report = intent.get("report") or ""
    is_income = module == "income"
    customer = intent.get("customer") or ""
    rows = []
    total = 0
    transaction_count = 0

    if result.get("formula") == "category_summary":
        for row in result.get("categories") or []:
            amount = int(row.get("income" if is_income else "expense") or 0)
            if amount:
                rows.append({
                    "date": "",
                    "category": row.get("category") or "Unknown",
                    "item": f"{row.get('transaction_count', 0)} transactions",
                    "payment": "",
                    "amount": amount,
                    "amount_received": row.get("amount_received", amount),
                    "outstanding_amount": row.get("outstanding_amount", 0),
                })
                total += amount
                transaction_count += int(row.get("transaction_count") or 0)
        total = int(result.get("total_income" if is_income else "total_expense", total) or 0)
        transaction_count = int(result.get("transaction_count", transaction_count) or 0)
    elif result.get("formula") == "list_transactions":
        for row in result.get("transactions") or []:
            amount = int(row.get("amount") or 0)
            rows.append({
                "date": row.get("Date") or "",
                "category": row.get("category") or "Unknown",
                "item": row.get("item") or "",
                "payment": row.get("payment_method") or "",
                "amount": amount,
                "amount_received": row.get("amount_received", amount if is_income else ""),
                "outstanding_amount": row.get("outstanding_amount", 0 if is_income else ""),
            })
            total += amount
        transaction_count = len(rows)
    elif result.get("formula") in {"top_expenses", "top_income"}:
        key = "income" if is_income else "expenses"
        for row in result.get(key) or []:
            amount = int(row.get("amount") or 0)
            rows.append({
                "date": row.get("Date") or "",
                "category": row.get("category") or "Unknown",
                "item": row.get("item") or "",
                "payment": row.get("payment_method") or "",
                "amount": amount,
                "amount_received": row.get("amount_received", amount if is_income else ""),
                "outstanding_amount": row.get("outstanding_amount", 0 if is_income else ""),
            })
            total += amount
        transaction_count = len(rows)
    elif result.get("formula") == "farm_transection_customer":
        for row in result.get("invoices") or []:
            rows.append({
                "date": row.get("invoice_date") or "",
                "invoice_number": row.get("invoice_number") or "",
                "category": "Farm Sales",
                "customer_name": row.get("customer_name") or customer or "",
                "item": row.get("item") or "Farm Sales",
                "payment": "Farm_Transection",
                "amount": int(row.get("total_amount") or 0),
                "amount_received": row.get("amount_received", 0),
                "outstanding_amount": row.get("outstanding_amount", 0),
                "note": row.get("note") or "",
            })
        total = int(result.get("total_sales") or sum(row.get("amount", 0) for row in rows) or 0)
        transaction_count = int(result.get("invoice_count") or len(rows))
    elif is_income:
        total = int(result.get("total_sales") or result.get("total_income") or 0)
        amount_received = int(result.get("amount_received") or total or 0)
        outstanding_amount = int(result.get("outstanding_amount") or 0)
        if total or amount_received or outstanding_amount:
            rows.append({
                "date": "",
                "category": "Farm Sales",
                "customer_name": customer or "Farm customer",
                "item": customer or report.replace("_", " ").title(),
                "payment": "Farm_Transection",
                "amount": total,
                "amount_received": amount_received,
                "outstanding_amount": outstanding_amount,
            })
            transaction_count = int(result.get("sources", {}).get("farm_transection_invoice_count") or 1)
    else:
        total = int(result.get("total_expense") or 0)
        transaction_count = int(result.get("expense_count") or 0)

    return {
        "kind": "farm_financial",
        "title": "Farm Income Report" if is_income else "Farm Expense Report",
        "report_name": report.replace("_", " ").title(),
        "period_label": result.get("_period_label") or result.get("period") or "",
        "total_label": "Total Farm Income" if is_income else "Total Farm Expense",
        "total": total,
        "transaction_count": transaction_count,
        "rows": rows,
        "is_income": is_income,
        "customer": customer,
    }


def _draw_header(pdf, title, question):
    pdf.text(50, 795, title, size=18, bold=True)
    pdf.text(50, 772, f"Question: {question}", size=10, max_width=495)
    pdf.text(50, 748, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", size=8)


def _unicode_voucher_lines(title, question, spec):
    lines = [
        title,
        f"Question: {question}",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        spec.get("title") or "Vouchers",
        "",
    ]
    vouchers = spec.get("vouchers") or []
    if not vouchers:
        lines.append("No vouchers found.")
        return lines

    lines.extend([
        f"Total: {_money(sum(int(row.get('total_amount') or 0) for row in vouchers))}",
        f"Paid: {_money(sum(int(row.get('amount_received') or 0) for row in vouchers))}",
        f"Outstanding: {_money(sum(int(row.get('outstanding_amount') or 0) for row in vouchers))}",
        "",
    ])
    for row in vouchers:
        lines.extend([
            f"Voucher {row.get('invoice_number') or '-'}",
            f"Date: {_unicode_value(row.get('invoice_date'))}",
            f"Customer: {_unicode_value(row.get('customer_name'))}",
            f"Item: {_unicode_value(row.get('item'))}",
            f"Qty: {_unicode_value(row.get('quantity'))}",
            f"Total: {_money(row.get('total_amount') or 0)}",
            f"Received: {_money(row.get('amount_received') or 0)}",
            f"Outstanding: {_money(row.get('outstanding_amount') or 0)}",
            f"Note: {_unicode_value(row.get('note'))}",
            "-" * 48,
        ])
    return lines


def _unicode_farm_lines(title, question, spec):
    lines = [
        title,
        f"Question: {question}",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        spec.get("title") or "Farm Report",
        f"Report: {spec.get('report_name') or '-'}",
        f"Period: {spec.get('period_label') or '-'}",
        f"{spec.get('total_label') or 'Total'}: {_money(spec.get('total') or 0)}",
        f"Records: {_money(spec.get('transaction_count') or 0)}",
        "",
        "Income Lines" if spec.get("is_income") else "Expense Lines",
        "",
    ]
    rows = spec.get("rows") or []
    if not rows:
        lines.append("No farm records found for this period.")
        return lines

    for row in rows:
        if spec.get("is_income"):
            lines.extend([
                f"Voucher {row.get('invoice_number') or '-'}",
                f"Date: {_unicode_value(row.get('date'))}",
                f"Customer: {_unicode_value(row.get('customer_name') or row.get('item'))}",
                f"Category: {_unicode_value(row.get('category'))}",
                f"Total: {_money(row.get('amount') or 0)}",
                f"Received: {_money(row.get('amount_received') or row.get('amount') or 0)}",
                f"Outstanding: {_money(row.get('outstanding_amount') or 0)}",
                f"Note: {_unicode_value(row.get('note'))}",
                "-" * 48,
            ])
        else:
            lines.extend([
                f"Date: {_unicode_value(row.get('date'))}",
                f"Category: {_unicode_value(row.get('category'))}",
                f"Description: {_unicode_value(row.get('item'))}",
                f"Payment: {_unicode_value(row.get('payment'))}",
                f"Amount: {_money(row.get('amount') or 0)}",
                "-" * 48,
            ])
    return lines


def _unicode_table_lines(title, question, spec):
    lines = [
        title,
        f"Question: {question}",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        spec.get("title") or "Report",
        "",
    ]
    for row in spec.get("table") or []:
        lines.append(" | ".join(_unicode_value(cell) for cell in row))
    return lines


def _unicode_pdf_lines(title, question, spec):
    kind = spec.get("kind")
    if kind == "voucher_cards":
        return _unicode_voucher_lines(title, question, spec)
    if kind == "farm_financial":
        return _unicode_farm_lines(title, question, spec)
    if spec.get("table"):
        return _unicode_table_lines(title, question, spec)
    return None


def _write_unicode_text_pdf(lines, output_path, title="BigShot Finance Report"):
    with tempfile.NamedTemporaryFile("w", suffix=".txt", encoding="utf-8", delete=False) as source:
        source.write("\n".join(str(line) for line in lines))
        source_path = source.name

    try:
        result = subprocess.run(
            [
                "cupsfilter",
                "-i",
                "text/plain",
                "-m",
                "application/pdf",
                "-t",
                title,
                source_path,
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if result.returncode == 0 and result.stdout.startswith(b"%PDF"):
            Path(output_path).write_bytes(result.stdout)
            return True
    except OSError:
        return False
    finally:
        try:
            Path(source_path).unlink(missing_ok=True)
        except OSError:
            pass
    return False


def _draw_bar(pdf, spec, x=70, y=455, width=420, height=235):
    values = [(label, abs(int(value or 0))) for label, value in _spec_values(spec) if int(value or 0) != 0][:12]
    if not values:
        pdf.text(x, y + height / 2, "No numeric values to chart.", size=11)
        return
    max_value = max(value for _, value in values) or 1
    label_width = 165
    value_width = 78
    bar_x = x + label_width + 12
    bar_width = max(90, width - label_width - value_width - 26)
    value_x = bar_x + bar_width + 10
    row_gap = 7
    row_height = max(17, min(25, (height - row_gap * (len(values) - 1)) / len(values)))
    pdf.line(bar_x, y, bar_x + bar_width, y, color=(190, 190, 190))
    for index, (label, value) in enumerate(values):
        yy = y + height - ((index + 1) * row_height) - (index * row_gap)
        drawn_width = max(1, bar_width * (value / max_value))
        pdf.text(x, yy + row_height - 4, label, size=7.3, bold=True, max_width=label_width)
        pdf.rect(bar_x, yy + 2, drawn_width, max(8, row_height - 4), fill=PALETTE[index % len(PALETTE)])
        pdf.text(value_x, yy + row_height - 5, _money(value), size=7.6, bold=True, max_width=value_width)


def _draw_stacked_bar(pdf, spec, x=70, y=455, width=420, height=235):
    rows = spec.get("rows", [])[:10]
    series = spec.get("series", [])
    if not rows or not series:
        _draw_bar(pdf, spec, x, y, width, height)
        return
    max_total = max(sum(abs(int(row.get(key, 0) or 0)) for _, key in series) for row in rows) or 1
    label_width = 155
    value_width = 70
    bar_x = x + label_width + 12
    bar_width = max(95, width - label_width - value_width - 26)
    value_x = bar_x + bar_width + 10
    bar_gap = 8
    bar_height = max(12, min(24, (height - bar_gap * (len(rows) - 1)) / len(rows)))
    for index, row in enumerate(rows):
        yy = y + height - ((index + 1) * bar_height) - (index * bar_gap)
        offset = 0
        row_total = sum(abs(int(row.get(key, 0) or 0)) for _, key in series)
        for s_index, (_, key) in enumerate(series):
            value = abs(int(row.get(key, 0) or 0))
            part_width = bar_width * (value / max_total)
            pdf.rect(bar_x + offset, yy, part_width, bar_height, fill=PALETTE[s_index % len(PALETTE)])
            offset += part_width
        pdf.text(x, yy + bar_height - 4, row.get(spec.get("label_key", "label"), ""), size=7.4, bold=True, max_width=label_width)
        pdf.text(value_x, yy + bar_height - 5, _money(row_total), size=7.6, bold=True, max_width=value_width)
    legend_x = x
    for s_index, (name, _) in enumerate(series):
        pdf.rect(legend_x, y - 28, 10, 10, fill=PALETTE[s_index % len(PALETTE)])
        pdf.text(legend_x + 14, y - 27, name, size=8)
        legend_x += 85


def _draw_pie(pdf, spec, cx=230, cy=570, radius=92):
    values = [(label, abs(int(value or 0))) for label, value in _spec_values(spec) if int(value or 0) != 0][:8]
    total = sum(value for _, value in values)
    if not total:
        pdf.text(70, cy, "No numeric values to chart.", size=11)
        return
    start = -math.pi / 2
    for index, (label, value) in enumerate(values):
        angle = (value / total) * math.pi * 2
        steps = max(3, int(angle / 0.18))
        points = [(cx, cy)]
        for step in range(steps + 1):
            theta = start + angle * (step / steps)
            points.append((cx + math.cos(theta) * radius, cy + math.sin(theta) * radius))
        pdf.polygon(points, PALETTE[index % len(PALETTE)])
        start += angle

    legend_x = 365
    legend_y = cy + radius - 5
    for index, (label, value) in enumerate(values):
        yy = legend_y - index * 18
        pdf.rect(legend_x, yy - 2, 9, 9, fill=PALETTE[index % len(PALETTE)])
        pdf.text(
            legend_x + 14,
            yy,
            f"{_short_label(label, 18)} {round(value / total * 100)}%",
            size=8,
            max_width=160,
        )


def _draw_box(pdf, spec, x=90, y=500, width=410):
    raw_values = spec.get("values", [])
    values = sorted(abs(int(value or 0)) for value in raw_values if int(value or 0) != 0)
    if len(values) < 2:
        pdf.text(70, y, "Not enough numeric values for a box and whisker plot.", size=11)
        return
    low, high = values[0], values[-1]
    q1 = _percentile(values, 0.25)
    median = _percentile(values, 0.5)
    q3 = _percentile(values, 0.75)
    scale = width / (high - low or 1)

    def px(value):
        return x + (value - low) * scale

    pdf.line(x, y, x + width, y, color=(70, 70, 70), width=1.2)
    pdf.line(px(low), y - 25, px(low), y + 25, color=(70, 70, 70), width=1.2)
    pdf.line(px(high), y - 25, px(high), y + 25, color=(70, 70, 70), width=1.2)
    pdf.rect(px(q1), y - 32, max(1, px(q3) - px(q1)), 64, fill=(224, 235, 250), stroke=(47, 128, 237))
    pdf.line(px(median), y - 35, px(median), y + 35, color=(235, 87, 87), width=2)
    pdf.text(x, y - 60, f"Min {_money(low)}", size=8)
    pdf.text(px(q1) - 20, y + 48, f"Q1 {_money(q1)}", size=8)
    pdf.text(px(median) - 24, y + 64, f"Median {_money(median)}", size=8)
    pdf.text(px(q3) - 20, y + 48, f"Q3 {_money(q3)}", size=8)
    pdf.text(x + width - 55, y - 60, f"Max {_money(high)}", size=8)


def _draw_table(pdf, table, start_y=365):
    if not table:
        return
    y = start_y
    col_count = max(len(row) for row in table)
    col_width = 495 / col_count
    for row_index, row in enumerate(table[:15]):
        wrapped = []
        line_count = 1
        for cell in row:
            text = _money(cell) if isinstance(cell, (int, float)) else str(cell)
            lines = _wrap_pdf_text(text, col_width - 8, 8.1)
            wrapped.append(lines)
            line_count = max(line_count, len(lines))
        row_height = max(22, 10 + line_count * 11)
        if y - row_height < 45:
            pdf.new_page()
            y = 785
        fill = (219, 226, 235) if row_index == 0 else ((244, 247, 251) if row_index % 2 == 0 else None)
        if fill:
            pdf.rect(50, y - row_height + 9, 495, row_height, fill=fill)
        for col_index, lines in enumerate(wrapped):
            for line_index, line in enumerate(lines):
                pdf.text(
                    54 + col_index * col_width,
                    y - (line_index * 11),
                    line,
                    size=8.1,
                    bold=True,
                    max_width=col_width - 8,
                )
        y -= row_height


def _draw_voucher_cards(pdf, vouchers, start_y=620):
    if not vouchers:
        pdf.text(50, start_y, "No vouchers found.", size=10)
        return

    card_width = 238
    card_height = 148
    gap = 19
    left_x = 50
    right_x = left_x + card_width + gap
    page_start_y = start_y
    page_capacity = 6
    index_on_page = 0

    for index, row in enumerate(vouchers):
        if index_on_page >= page_capacity:
            pdf.new_page()
            pdf.text(50, 795, "Sote Phwar Vouchers", size=16, bold=True)
            page_start_y = 750
            page_capacity = 8
            index_on_page = 0

        x = left_x if index_on_page % 2 == 0 else right_x
        y = page_start_y - ((index_on_page // 2) * (card_height + 12))

        pdf.rect(x, y - card_height, card_width, card_height, fill=(246, 248, 251), stroke=(130, 145, 166))
        pdf.rect(x, y - 22, card_width, 22, fill=(218, 226, 236))
        pdf.text(x + 8, y - 16, f"Voucher {row.get('invoice_number') or '-'}", size=10.5, bold=True, max_width=card_width - 16)

        details = [
            ("Date", row.get("invoice_date") or "-"),
            ("Customer", row.get("customer_name") or "-"),
            ("Item", row.get("item") or "-"),
            ("Qty", _money(row.get("quantity", 0))),
            ("Total", _money(row.get("total_amount", 0))),
            ("Received", _money(row.get("amount_received", 0))),
            ("Outstanding", _money(row.get("outstanding_amount", 0))),
            ("Note", row.get("note") or "-"),
        ]
        line_y = y - 40
        for label, value in details:
            pdf.text(x + 8, line_y, f"{label}:", size=8.4, bold=True, max_width=62)
            used = pdf.text(x + 68, line_y, value, size=8.4, bold=True, max_width=card_width - 78)
            line_y -= max(12, used)
            if line_y < y - card_height + 8:
                break
        index_on_page += 1


def _draw_voucher_summary(pdf, vouchers, x=50, y=698):
    totals = [
        ("Total", sum(int(row.get("total_amount") or 0) for row in vouchers)),
        ("Paid", sum(int(row.get("amount_received") or 0) for row in vouchers)),
        ("Outstanding", sum(int(row.get("outstanding_amount") or 0) for row in vouchers)),
    ]
    cell_width = 165
    cell_height = 42
    for index, (label, value) in enumerate(totals):
        cell_x = x + (cell_width * index)
        pdf.rect(cell_x, y - cell_height, cell_width, cell_height, fill=(246, 248, 251), stroke=(130, 145, 166))
        pdf.text(cell_x + 10, y - 15, label, size=8.8, bold=True, color=(75, 85, 99))
        pdf.text(cell_x + 10, y - 33, _money(value), size=13, bold=True)


def _stock_quantity(row):
    for key in ("stock_qty", "quantity", "qty", "stock"):
        if key in row:
            try:
                return int(row.get(key) or 0)
            except (TypeError, ValueError):
                return 0
    return 0


def _stock_status(quantity):
    if quantity <= 0:
        return "Out of Stock", (237, 225, 225), (176, 48, 48)
    if quantity <= 10:
        return "Low Stock", (255, 244, 214), (160, 99, 18)
    return "In Stock", (223, 241, 229), (35, 120, 73)


def _draw_stock_sheet_header(pdf, y):
    pdf.rect(50, y - 6, 495, 24, fill=(218, 226, 236))
    pdf.text(58, y, "Store", size=8.8, bold=True)
    pdf.text(192, y, "Product", size=8.8, bold=True)
    pdf.text(390, y, "Qty", size=8.8, bold=True)
    pdf.text(445, y, "Status", size=8.8, bold=True)


def _draw_stock_summary_box(pdf, x, y, label, value, fill):
    pdf.rect(x, y - 44, 112, 44, fill=fill, stroke=(183, 195, 210))
    pdf.text(x + 9, y - 15, label, size=8.4, bold=True, color=(75, 85, 99))
    pdf.text(x + 9, y - 34, _money(value), size=14, bold=True)


def _draw_stock_sheet(pdf, rows, start_y=688):
    if not rows:
        pdf.text(50, start_y, "No stock found.", size=10)
        return

    normalized = [
        {
            "store": row.get("store") or row.get("location") or "-",
            "product": row.get("product") or row.get("item") or "-",
            "quantity": _stock_quantity(row),
        }
        for row in rows
    ]
    total_qty = sum(row["quantity"] for row in normalized)
    low_count = sum(1 for row in normalized if 0 < row["quantity"] <= 10)
    out_count = sum(1 for row in normalized if row["quantity"] <= 0)

    pdf.text(50, start_y, "Stock Summary", size=11.5, bold=True)
    summary_y = start_y - 18
    _draw_stock_summary_box(pdf, 50, summary_y, "Total SKUs", len(normalized), (242, 246, 251))
    _draw_stock_summary_box(pdf, 178, summary_y, "Total Qty", total_qty, (239, 247, 243))
    _draw_stock_summary_box(pdf, 306, summary_y, "Low Stock", low_count, (255, 248, 229))
    _draw_stock_summary_box(pdf, 433, summary_y, "Out of Stock", out_count, (249, 233, 233))

    y = start_y - 92
    _draw_stock_sheet_header(pdf, y)
    y -= 28
    row_height = 24

    for index, row in enumerate(normalized):
        if y < 65:
            pdf.new_page()
            pdf.text(50, 795, "Sote Phwar Inventory Stock", size=16, bold=True)
            y = 755
            _draw_stock_sheet_header(pdf, y)
            y -= 28

        fill = (246, 248, 251) if index % 2 == 0 else None
        if fill:
            pdf.rect(50, y - 7, 495, row_height, fill=fill)

        status, badge_fill, badge_text = _stock_status(row["quantity"])
        pdf.text(58, y, _short_label(row["store"], 24), size=8.4, bold=True, max_width=126)
        pdf.text(192, y, _short_label(row["product"], 36), size=8.4, bold=True, max_width=188)
        pdf.text(390, y, _money(row["quantity"]), size=8.8, bold=True, max_width=45)
        pdf.rect(443, y - 5, 84, 17, fill=badge_fill, stroke=(210, 215, 222))
        pdf.text(450, y, status, size=7.8, bold=True, color=badge_text, max_width=72)
        y -= row_height


def _draw_farm_metric_box(pdf, x, y, label, value, fill):
    pdf.rect(x, y - 52, 155, 52, fill=fill, stroke=(181, 194, 203))
    pdf.text(x + 10, y - 17, label, size=8.6, bold=True, color=(75, 85, 99))
    pdf.text(x + 10, y - 39, _money(value), size=14.5, bold=True)


def _draw_farm_report_rows(pdf, rows, start_y):
    pdf.rect(50, start_y - 6, 495, 25, fill=(216, 226, 220))
    pdf.text(58, start_y, "Date", size=8.4, bold=True)
    pdf.text(122, start_y, "Category", size=8.4, bold=True)
    pdf.text(248, start_y, "Description", size=8.4, bold=True)
    pdf.text(405, start_y, "Payment", size=8.4, bold=True)
    pdf.text(476, start_y, "Amount", size=8.4, bold=True)

    y = start_y - 29
    row_height = 24
    if not rows:
        pdf.text(58, y, "No farm records found for this period.", size=9)
        return

    for index, row in enumerate(rows):
        category_lines = _wrap_pdf_text(row.get("category") or "-", 116, 8.1)
        item_lines = _wrap_pdf_text(row.get("item") or "-", 146, 8.1)
        line_count = max(len(category_lines), len(item_lines), 1)
        row_height = max(24, 13 + (line_count * 11))

        if y - row_height < 50:
            pdf.new_page()
            pdf.text(50, 795, "Farm Income and Expense Report", size=16, bold=True)
            y = 755
            pdf.rect(50, y - 6, 495, 25, fill=(216, 226, 220))
            pdf.text(58, y, "Date", size=8.4, bold=True)
            pdf.text(122, y, "Category", size=8.4, bold=True)
            pdf.text(248, y, "Description", size=8.4, bold=True)
            pdf.text(405, y, "Payment", size=8.4, bold=True)
            pdf.text(476, y, "Amount", size=8.4, bold=True)
            y -= 29

        fill = (246, 249, 246) if index % 2 == 0 else None
        if fill:
            pdf.rect(50, y - row_height + 10, 495, row_height, fill=fill)
        pdf.text(58, y, _short_label(row.get("date") or "-", 12), size=8.1, bold=True, max_width=58)
        for line_index, line in enumerate(category_lines):
            pdf.text(122, y - (line_index * 11), line, size=8.1, bold=True, max_width=116)
        for line_index, line in enumerate(item_lines):
            pdf.text(248, y - (line_index * 11), line, size=8.1, bold=True, max_width=146)
        pdf.text(405, y, _short_label(row.get("payment") or "-", 14), size=8.1, bold=True, max_width=62)
        pdf.text(476, y, _money(row.get("amount") or 0), size=8.1, bold=True, max_width=62)
        y -= row_height


def _draw_farm_income_cards(pdf, rows, start_y=550):
    if not rows:
        pdf.text(58, start_y, "No farm income records found for this period.", size=9)
        return

    card_width = 238
    card_height = 126
    gap = 19
    left_x = 50
    right_x = left_x + card_width + gap
    page_start_y = start_y
    page_capacity = 6
    index_on_page = 0

    for index, row in enumerate(rows):
        if index_on_page >= page_capacity:
            pdf.new_page()
            pdf.text(50, 795, "Farm Income Lines", size=16, bold=True)
            page_start_y = 750
            page_capacity = 8
            index_on_page = 0

        x = left_x if index_on_page % 2 == 0 else right_x
        y = page_start_y - ((index_on_page // 2) * (card_height + 12))

        customer = row.get("customer_name") or row.get("item") or "-"
        voucher = row.get("invoice_number") or "-"
        pdf.rect(x, y - card_height, card_width, card_height, fill=(246, 249, 246), stroke=(130, 145, 166))
        pdf.rect(x, y - 22, card_width, 22, fill=(216, 226, 220))
        pdf.text(x + 8, y - 16, f"Voucher {voucher}", size=10.5, bold=True, max_width=card_width - 16)

        details = [
            ("Date", row.get("date") or "-"),
            ("Customer", customer),
            ("Category", row.get("category") or "Farm Sales"),
            ("Total", _money(row.get("amount", 0))),
            ("Received", _money(row.get("amount_received", row.get("amount", 0)))),
            ("Outstanding", _money(row.get("outstanding_amount", 0))),
            ("Note", row.get("note") or "-"),
        ]
        line_y = y - 40
        for label, value in details:
            pdf.text(x + 8, line_y, f"{label}:", size=8.4, bold=True, max_width=62)
            used = pdf.text(x + 72, line_y, value, size=8.4, bold=True, max_width=card_width - 82)
            line_y -= max(12, used)
            if line_y < y - card_height + 8:
                break
        index_on_page += 1


def _draw_farm_financial_report(pdf, spec, start_y=720):
    pdf.text(50, start_y, spec["title"], size=13, bold=True)
    pdf.text(50, start_y - 20, f"Report: {spec.get('report_name') or '-'}", size=9.2, bold=True)
    pdf.text(50, start_y - 36, f"Period: {spec.get('period_label') or '-'}", size=9.2, bold=True)

    total_fill = (225, 242, 232) if spec.get("is_income") else (249, 232, 225)
    _draw_farm_metric_box(pdf, 50, start_y - 65, spec["total_label"], spec.get("total", 0), total_fill)
    _draw_farm_metric_box(pdf, 220, start_y - 65, "Records", spec.get("transaction_count", 0), (242, 246, 241))
    average = int((spec.get("total") or 0) / spec.get("transaction_count")) if spec.get("transaction_count") else 0
    _draw_farm_metric_box(pdf, 390, start_y - 65, "Average", average, (239, 245, 248))

    section = "Income Lines" if spec.get("is_income") else "Expense Lines"
    pdf.text(50, start_y - 145, section, size=11.2, bold=True)
    if spec.get("is_income"):
        _draw_farm_income_cards(pdf, spec.get("rows") or [], start_y - 170)
    else:
        _draw_farm_report_rows(pdf, spec.get("rows") or [], start_y - 170)


def create_chart_pdf_report(question, output_path, title="BigShot Finance Report"):
    formula_name = choose_formula(question)
    if formula_name not in FAST_FORMULAS:
        result = {"formula": "analysis"}
        spec = None
    else:
        result = run_formula(formula_name, question)
        spec = _chart_spec(result, question)

    return create_chart_pdf_report_from_result(result, question, output_path, title=title, spec=spec)


def create_chart_pdf_report_from_result(result, question, output_path, title="BigShot Finance Report", spec=None):
    if spec is None:
        spec = _chart_spec(result, question)

    if not spec:
        return False

    if (
        _contains_non_ascii(result)
        or _contains_non_ascii(spec)
        or _contains_non_ascii(question)
        or _contains_non_ascii(title)
    ):
        unicode_lines = _unicode_pdf_lines(title, question, spec)
        if unicode_lines and _write_unicode_text_pdf(unicode_lines, output_path, title=title):
            return True

    pdf = PdfCanvas(title)
    _draw_header(pdf, title, question)

    kind = spec.get("kind")
    if kind == "voucher_cards":
        pdf.text(50, 720, spec["title"], size=12, bold=True)
        vouchers = spec.get("vouchers") or []
        _draw_voucher_summary(pdf, vouchers, y=698)
        _draw_voucher_cards(pdf, vouchers, start_y=638)
        pdf.finish(output_path)
        return True

    if kind == "stock_sheet":
        pdf.text(50, 720, spec["title"], size=12, bold=True)
        _draw_stock_sheet(pdf, spec.get("stock") or [], start_y=698)
        pdf.finish(output_path)
        return True

    if kind == "farm_financial":
        _draw_farm_financial_report(pdf, spec, start_y=720)
        pdf.finish(output_path)
        return True

    pdf.text(50, 720, spec["title"], size=12, bold=True)

    if kind == "table":
        _draw_table(pdf, spec.get("table"), start_y=690)
        pdf.finish(output_path)
        return True

    if kind == "pie":
        _draw_pie(pdf, spec)
    elif kind == "stacked_bar":
        _draw_stacked_bar(pdf, spec)
    elif kind == "box":
        _draw_box(pdf, spec)
    else:
        _draw_bar(pdf, spec)

    pdf.text(50, 415, "Data Table", size=12, bold=True)
    _draw_table(pdf, spec.get("table"), start_y=392)
    pdf.finish(output_path)
    return True


def _spec_values(spec):
    if spec.get("values"):
        return spec["values"]

    rows = spec.get("rows") or []
    series = spec.get("series") or []
    label_key = spec.get("label_key", "label")
    if rows and series:
        return [
            (
                row.get(label_key, ""),
                sum(abs(int(row.get(key, 0) or 0)) for _, key in series),
            )
            for row in rows
        ]

    return []
