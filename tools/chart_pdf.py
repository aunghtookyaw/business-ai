import math
import json
import re
import subprocess
import tempfile
import textwrap
from io import BytesIO
from datetime import date, datetime
from pathlib import Path

from business_agent import FAST_FORMULAS, choose_formula
from tools.ollama_client import ask_ai
from tools.pdf_utils import (
    ENGLISH_FONT_NAME,
    MYANMAR_FONT_NAME,
    contains_myanmar_value,
    ensure_myanmar_font_registered,
    font_for_text,
)
from tools.formula_engine import (
    calculate_inventory_value,
    cash_flow,
    category_summary,
    expense_total,
    kpi_overview,
    normalize_period,
    sales_total,
    sector_summary,
    sotephwar_inventory_movement_summary,
    sotephwar_inventory_stock,
    sotephwar_transection_summary,
    top_income,
    run_formula,
)


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
    label = " ".join(str(value).split())
    if len(label) <= length:
        return label
    return label[:length - 3].rstrip() + "..."


def _wrap_pdf_text(value, width, size):
    chars = max(8, int(width / (size * 0.52)))
    return textwrap.wrap(" ".join(str(value).split()) or "-", width=chars) or ["-"]


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


def _mmk(value):
    return f"{int(value or 0):,} MMK"


def _display_date(value):
    text = str(value or "").strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).strftime("%d %B %Y").lstrip("0")
        except ValueError:
            pass
    return text or "-"


def _ledger_description(row):
    parts = []
    description = row.get("description")
    category = row.get("category")
    customer = row.get("customer")
    if description:
        parts.append(str(description))
    if category and category != "-" and category not in parts[0:1]:
        parts.append(str(category))
    if customer and all(customer not in part for part in parts):
        parts.append(str(customer))
    return " - ".join(parts) or "-"


def _period_months(count=12, today=None):
    today = today or date.today()
    months = []
    year = today.year
    month = today.month
    for _ in range(count):
        months.append((year, month))
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    return list(reversed(months))


def _month_period(year, month):
    return f"month:{year}-{month:02d}"


def _month_label(year, month):
    return date(year, month, 1).strftime("%b %Y")


def _change_percent(current, previous):
    previous = int(previous or 0)
    if not previous:
        return None
    return round(((int(current or 0) - previous) / previous) * 100, 1)


class PdfCanvas:
    def __init__(self, title, use_reportlab=False):
        self.title = title
        self.pages = []
        self.width = 595
        self.height = 842
        self._content = []
        self._use_reportlab = use_reportlab
        self._buffer = None
        self._canvas = None
        if self._use_reportlab:
            ensure_myanmar_font_registered()
            from reportlab.pdfgen import canvas

            self._buffer = BytesIO()
            self._canvas = canvas.Canvas(
                self._buffer,
                pagesize=(self.width, self.height),
                pageCompression=0,
                invariant=1,
            )

    def new_page(self):
        if self._use_reportlab:
            self._canvas.showPage()
            return
        if self._content:
            self.pages.append("\n".join(self._content).encode("latin-1"))
        self._content = []

    def finish(self, output_path):
        if self._use_reportlab:
            self._canvas.save()
            Path(output_path).write_bytes(self._buffer.getvalue())
            return
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
        if self._use_reportlab:
            r, g, b = [component / 255 for component in rgb]
            self._canvas.setFillColorRGB(r, g, b)
            self._canvas.setStrokeColorRGB(r, g, b)
            return
        r, g, b = [component / 255 for component in rgb]
        self._content.append(f"{r:.3f} {g:.3f} {b:.3f} rg {r:.3f} {g:.3f} {b:.3f} RG")

    def stroke_color(self, rgb):
        if self._use_reportlab:
            r, g, b = [component / 255 for component in rgb]
            self._canvas.setStrokeColorRGB(r, g, b)
            return
        r, g, b = [component / 255 for component in rgb]
        self._content.append(f"{r:.3f} {g:.3f} {b:.3f} RG")

    def line_width(self, width):
        if self._use_reportlab:
            self._canvas.setLineWidth(width)
            return
        self._content.append(f"{width:.2f} w")

    def text(self, x, y, text, size=10, bold=False, max_width=None, color=(17, 24, 39)):
        if self._use_reportlab:
            lines = [str(text)]
            if max_width:
                chars = max(8, int(max_width / (size * 0.52)))
                lines = textwrap.wrap(str(text), width=chars) or [""]
            r, g, b = [component / 255 for component in color]
            self._canvas.setFillColorRGB(r, g, b)
            for index, line in enumerate(lines):
                yy = y - (index * (size + 3))
                font = font_for_text(line)
                if font == ENGLISH_FONT_NAME and bold:
                    font = "Helvetica-Bold"
                self._canvas.setFont(font, size)
                self._canvas.drawString(x, yy, line)
            return len(lines) * (size + 3)
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
        if self._use_reportlab:
            fill_flag = 1 if fill else 0
            stroke_flag = 1 if stroke else 0
            if fill:
                r, g, b = [component / 255 for component in fill]
                self._canvas.setFillColorRGB(r, g, b)
            if stroke:
                r, g, b = [component / 255 for component in stroke]
                self._canvas.setStrokeColorRGB(r, g, b)
            self._canvas.rect(x, y, width, height, fill=fill_flag, stroke=stroke_flag)
            return
        if fill:
            self.color(fill)
            self._content.append(f"{x:.2f} {y:.2f} {width:.2f} {height:.2f} re f")
        if stroke:
            self.stroke_color(stroke)
            self._content.append(f"{x:.2f} {y:.2f} {width:.2f} {height:.2f} re S")

    def line(self, x1, y1, x2, y2, color=(60, 60, 60), width=1):
        if self._use_reportlab:
            r, g, b = [component / 255 for component in color]
            self._canvas.setStrokeColorRGB(r, g, b)
            self._canvas.setLineWidth(width)
            self._canvas.line(x1, y1, x2, y2)
            return
        self.stroke_color(color)
        self.line_width(width)
        self._content.append(f"{x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S")

    def polygon(self, points, fill):
        if not points:
            return
        if self._use_reportlab:
            r, g, b = [component / 255 for component in fill]
            self._canvas.setFillColorRGB(r, g, b)
            path = self._canvas.beginPath()
            first = points[0]
            path.moveTo(first[0], first[1])
            for x, y in points[1:]:
                path.lineTo(x, y)
            path.close()
            self._canvas.drawPath(path, fill=1, stroke=0)
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


def _business_title(intent):
    business = intent.get("business")
    if business == "sote_phwar":
        return "Sote Phwar"
    if business == "farm":
        return "Farm"
    return ""


def _module_title(intent):
    return "Income" if intent.get("module") == "income" else "Expense"


def _financial_totals(result, amount_key):
    total_key = "total_income" if amount_key == "income" else "total_expense"
    total = int(
        result.get(total_key)
        or result.get("total_sales")
        or result.get("total_amount")
        or result.get("Total_Amount")
        or 0
    )
    rows = result.get("categories") or result.get("transactions") or result.get("invoices") or []
    if not total and rows:
        row_amount_key = "amount" if result.get("transactions") else ("total_amount" if result.get("invoices") else amount_key)
        total = sum(int(row.get(row_amount_key) or 0) for row in rows)
    if result.get("amount_received") is not None:
        received = int(result.get("amount_received") or 0)
    elif result.get("Total_Received") is not None:
        received = int(result.get("Total_Received") or 0)
    elif result.get("received") is not None:
        received = int(result.get("received") or 0)
    else:
        received = 0
    if received == 0 and "amount_received" not in result and "Total_Received" not in result and "received" not in result:
        received = sum(int(row.get("amount_received") or 0) for row in rows)
    if received == 0 and "amount_received" not in result and "Total_Received" not in result and "received" not in result and total:
        received = total
    if result.get("outstanding_amount") is not None:
        outstanding = int(result.get("outstanding_amount") or 0)
    elif result.get("Outstanding_Balance") is not None:
        outstanding = int(result.get("Outstanding_Balance") or 0)
    else:
        outstanding = 0
    if outstanding == 0 and "outstanding_amount" not in result and "Outstanding_Balance" not in result:
        outstanding = sum(int(row.get("outstanding_amount") or 0) for row in rows)
    return total, received, outstanding


def _financial_trend_filters(intent, income_expense):
    filters = {}
    business = intent.get("business")
    if business == "sote_phwar":
        filters["sector"] = "Sote Phwar"
    elif business == "farm":
        filters["sector"] = "Farm"
    elif business == "extension":
        filters["sector"] = "SP Extension"
    if income_expense:
        filters["income_expense"] = income_expense
    return filters


def _financial_total_trend(intent, amount_key, month_count=6):
    values = []
    income_expense = "Income" if amount_key == "income" else "Expense"
    filters = _financial_trend_filters(intent, income_expense)
    for year, month in _period_months(month_count):
        period = _month_period(year, month)
        label = _month_label(year, month)
        if amount_key == "income" and intent.get("business") == "sote_phwar":
            row = _safe_call(sotephwar_transection_summary, period, default={})
            amount = int(row.get("total_amount") or 0)
        elif amount_key == "income":
            row = _safe_call(sales_total, period, filters, default={})
            amount = int(row.get("total_sales") or row.get("total_income") or 0)
        else:
            row = _safe_call(expense_total, period, filters, default={})
            amount = int(row.get("total_expense") or 0)
        values.append((label, amount))
    return values


def _financial_total_spec(result, intent, amount_key):
    total, received, outstanding = _financial_totals(result, amount_key)
    module_title = "Income" if amount_key == "income" else "Expense"
    business_title = _business_title(intent)
    title = f"{business_title} - {module_title} - Total {module_title}".strip(" -")
    row_count = result.get("expense_count", result.get("invoice_count", result.get("transaction_count", 0)))
    show_collection = amount_key == "income"
    table = [
        ("Metric", "Amount"),
        (f"Total {module_title}", total),
    ]
    if show_collection:
        table.extend([
            ("Received", received),
            ("Outstanding", outstanding),
        ])
    table.append(("Rows", row_count))
    return {
        "kind": "financial_total_report",
        "title": title,
        "amount_label": f"Total {module_title}",
        "module": module_title,
        "show_collection": show_collection,
        "row_count": row_count,
        "total": total,
        "received": received,
        "outstanding": outstanding,
        "values": [("Received", received), ("Outstanding", outstanding)] if show_collection else [(f"Total {module_title}", total)],
        "trend_title": f"Monthly {module_title} Trend",
        "trend_values": _financial_total_trend(intent, amount_key),
        "table": table,
    }


def _is_financial_total_spec(spec):
    return spec.get("kind") == "financial_total_report"


def _is_farm_total_income_spec(result, spec):
    intent = result.get("_bi_intent") or {}
    return (
        spec.get("kind") == "financial_total_report"
        and intent.get("business") == "farm"
        and intent.get("module") == "income"
        and intent.get("report") == "total_income"
    )


def _should_use_unicode_text_pdf(result, spec, question, title):
    return (
        _contains_non_ascii(result)
        or _contains_non_ascii(spec)
        or _contains_non_ascii(question)
        or _contains_non_ascii(title)
    )


def _financial_category_spec(result, intent, report, amount_key):
    rows = result.get("categories") or []
    total, received, outstanding = _financial_totals(result, amount_key)
    business_title = _business_title(intent)
    module_title = "Income" if amount_key == "income" else "Expense"
    title_kind = "Summary" if report in {"income_summary", "expense_summary"} else "by Category"
    title = f"{business_title} {module_title} {title_kind}".strip()
    transaction_count = int(result.get("transaction_count", sum(row.get("transaction_count", 0) for row in rows)) or 0)
    show_collection = amount_key == "income"
    if show_collection:
        table = [("Category", module_title, "Received", "Outstanding", "Rows")] + [
            (
                row.get("category") or "-",
                row.get(amount_key) or abs(row.get("net", 0)),
                row.get("amount_received", row.get(amount_key) or abs(row.get("net", 0))),
                row.get("outstanding_amount", 0),
                row.get("transaction_count", 0),
            )
            for row in rows
        ] + [("Total", total, received, outstanding, transaction_count)]
    else:
        table = [("Category", module_title, "Rows")] + [
            (
                row.get("category") or "-",
                row.get(amount_key) or abs(row.get("net", 0)),
                row.get("transaction_count", 0),
            )
            for row in rows
        ] + [("Total", total, transaction_count)]
    return {
        "kind": "financial_category_report",
        "title": title,
        "amount_label": f"Total {module_title}",
        "module": module_title,
        "show_collection": show_collection,
        "row_count": transaction_count,
        "category_count": len(rows),
        "chart_title": f"{module_title} Categories",
        "table_title": f"{module_title} Category Table",
        "total": total,
        "received": received,
        "outstanding": outstanding,
        "values": [(row.get("category") or "-", row.get(amount_key) or abs(row.get("net", 0))) for row in rows],
        "table": table,
    }


def _financial_detail_spec(result, intent, amount_key):
    rows = result.get("transactions") or result.get("invoices") or []
    total, received, outstanding = _financial_totals(result, amount_key)
    business_title = _business_title(intent)
    module_title = "Income" if amount_key == "income" else "Expense"
    amount_field = "amount" if result.get("transactions") else "total_amount"
    return {
        "kind": "transaction_ledger_report",
        "title": f"{business_title} {module_title} Detail".strip(),
        "amount_label": f"Total {module_title}",
        "business": business_title,
        "module": module_title,
        "period_label": result.get("_period_label") or result.get("period") or "-",
        "customer": intent.get("customer"),
        "category": intent.get("category") or ", ".join(intent.get("categories") or []),
        "total": total,
        "received": received,
        "outstanding": outstanding,
        "transactions": [
            {
                "date": row.get("Date") or row.get("invoice_date") or "-",
                "description": row.get("item") or row.get("customer_name") or row.get("category") or "-",
                "category": row.get("category") or "-",
                "customer": row.get("customer_name") or "",
                "payment": row.get("payment_method") or row.get("payment") or "-",
                "amount": row.get(amount_field, 0),
            }
            for row in rows
        ],
    }


def _income_summary_product(row, business):
    if business == "sote_phwar":
        return row.get("product") or row.get("category") or "Sote Phwar Sales"
    if business == "farm":
        return row.get("product") or row.get("category") or "Farm Sales"
    return row.get("product") or row.get("category") or row.get("item") or "Sales"


def _income_summary_rows(result, intent):
    business = intent.get("business") or ""
    if not business and result.get("formula") == "sotephwar_transection_summary":
        business = "sote_phwar"
    rows = []
    if result.get("formula") == "top_income":
        source_rows = result.get("income") or []
    elif result.get("formula") == "category_summary":
        source_rows = result.get("categories") or []
    elif result.get("formula") == "sotephwar_transection_summary":
        source_rows = result.get("customers") or []
    else:
        source_rows = result.get("income") or result.get("categories") or result.get("customers") or []

    for row in source_rows:
        total = int(row.get("total_amount") or row.get("amount") or row.get("income") or row.get("net") or 0)
        if not total:
            continue
        received = row.get("amount_received")
        received = int(total if received is None else received or 0)
        outstanding = int(row.get("outstanding_amount") or max(total - received, 0))
        rows.append({
            "date": row.get("Date") or row.get("invoice_date") or row.get("date") or "-",
            "customer": row.get("customer_name") or row.get("customer") or row.get("item") or row.get("category") or "-",
            "sector": row.get("sector") or ("Sote Phwar" if business == "sote_phwar" else "Farm" if business == "farm" else "-"),
            "product": _income_summary_product(row, business),
            "total_amount": total,
            "amount_received": received,
            "outstanding_amount": outstanding,
            "row_count": int(row.get("invoice_count") or row.get("transaction_count") or 0),
        })

    rows.sort(key=lambda row: row["total_amount"], reverse=True)
    total = int(
        result.get("total_amount")
        or result.get("total_income")
        or sum(row["total_amount"] for row in rows)
        or 0
    )
    received = int(
        result.get("amount_received")
        or sum(row["amount_received"] for row in rows)
        or 0
    )
    outstanding = int(
        result.get("outstanding_amount")
        or sum(row["outstanding_amount"] for row in rows)
        or 0
    )
    if not rows and total:
        rows.append({
            "date": "-",
            "customer": "All Customers",
            "sector": "Sote Phwar" if business == "sote_phwar" else "Farm" if business == "farm" else "-",
            "product": "Sote Phwar Sales" if business == "sote_phwar" else "Farm Sales" if business == "farm" else "Sales",
            "total_amount": total,
            "amount_received": received,
            "outstanding_amount": outstanding,
            "row_count": int(result.get("invoice_count") or result.get("transaction_count") or 0),
        })

    business_title = "Sote Phwar" if business == "sote_phwar" else "Farm" if business == "farm" else _business_title(intent)
    return {
        "kind": "income_summary_report",
        "title": f"{business_title} Income Summary".strip() or "Income Summary",
        "chart_title": "Top Income by Customer",
        "table_title": "Income Summary Table",
        "total": total,
        "received": received,
        "outstanding": outstanding,
        "rows": rows,
        "series": [("Paid", "amount_received"), ("Outstanding", "outstanding_amount")],
        "label_key": "customer",
        "table": [("Date", "Customer", "Sector", "Category / Product", "Total Amount", "Total Received", "Outstanding Balance")] + [
            (
                row["date"],
                row["customer"],
                row["sector"],
                row["product"],
                row["total_amount"],
                row["amount_received"],
                row["outstanding_amount"],
            )
            for row in rows
        ],
    }


def _income_category_business(result, intent):
    business = intent.get("business") or ""
    if not business and result.get("formula") == "sotephwar_product_ranking":
        business = "sote_phwar"
    if not business and result.get("formula") == "farm_product_ranking":
        business = "farm"
    return business


def _income_category_trend(intent, business, month_count=6):
    filters = {"income_expense": "Income"}
    if business == "sote_phwar":
        filters["sector"] = "Sote Phwar"
    elif business == "farm":
        filters["sector"] = "Farm"
    rows = []
    for year, month in _period_months(month_count):
        period = _month_period(year, month)
        label = _month_label(year, month)
        row = _safe_call(sales_total, period, filters, default={})
        rows.append({
            "label": label,
            "received": int(row.get("amount_received") or row.get("Total_Received") or 0),
            "outstanding": int(row.get("outstanding_amount") or row.get("Outstanding_Balance") or 0),
        })
    return rows


def _income_category_spec(result, intent):
    business = _income_category_business(result, intent)
    business_title = "Sote Phwar" if business == "sote_phwar" else "Farm" if business == "farm" else _business_title(intent)
    title = f"{business_title} - Income - Income by Category".strip(" -")
    source_rows = []
    if result.get("formula") in {"sotephwar_product_ranking", "farm_product_ranking"}:
        source_rows = result.get("products") or []
    else:
        source_rows = result.get("categories") or []

    rows = []
    for row in source_rows:
        product = row.get("product") or row.get("category") or row.get("item") or (
            "Sote Phwar Sales" if business == "sote_phwar" else "Farm Sales" if business == "farm" else "Sales"
        )
        total = int(row.get("total_amount") or row.get("Total_Amount") or row.get("income") or row.get("amount") or 0)
        received = row.get("amount_received")
        if received is None:
            received = row.get("Total_Received")
        received = int(total if received is None else received or 0)
        outstanding = row.get("outstanding_amount")
        if outstanding is None:
            outstanding = row.get("Outstanding_Balance")
        outstanding = int(max(total - received, 0) if outstanding is None else outstanding or 0)
        quantity = row.get("quantity")
        rows.append({
            "product": product,
            "quantity": "" if quantity is None else int(quantity or 0),
            "total_amount": total,
            "amount_received": received,
            "outstanding_amount": outstanding,
            "collection_percent": round((received / total) * 100, 1) if total else 0,
        })

    rows.sort(key=lambda row: row["total_amount"], reverse=True)
    total = int(result.get("total_amount") or result.get("total_income") or result.get("Total_Amount") or sum(row["total_amount"] for row in rows) or 0)
    received = int(result.get("amount_received") or result.get("Total_Received") or sum(row["amount_received"] for row in rows) or 0)
    outstanding = int(result.get("outstanding_amount") or result.get("Outstanding_Balance") or sum(row["outstanding_amount"] for row in rows) or 0)
    if not rows and total:
        rows.append({
            "product": "Sote Phwar Sales" if business == "sote_phwar" else "Farm Sales" if business == "farm" else "Sales",
            "quantity": "",
            "total_amount": total,
            "amount_received": received,
            "outstanding_amount": outstanding,
            "collection_percent": round((received / total) * 100, 1) if total else 0,
        })

    return {
        "kind": "income_category_report",
        "title": title or "Income by Category",
        "total": total,
        "received": received,
        "outstanding": outstanding,
        "trend_rows": _income_category_trend(intent, business),
        "rows": rows,
        "table": [("Category/Product", "Quantity", "Total Amount", "Total Received", "Outstanding Balance", "Collection %")] + [
            (
                row["product"],
                row["quantity"],
                row["total_amount"],
                row["amount_received"],
                row["outstanding_amount"],
                f"{row['collection_percent']}%",
            )
            for row in rows
        ],
    }


def _income_detail_report_spec(result, intent):
    rows = result.get("rows") or []
    kpis = result.get("kpis") or {}
    footer = result.get("footer") or {}
    business_title = result.get("sector") or _business_title(intent)
    title = result.get("_report_title") or f"{business_title} - Income - Income Detail".strip(" -")
    total = int(kpis.get("total_income") or footer.get("total_income") or sum(int(row.get("total") or 0) for row in rows))
    received = int(kpis.get("total_received") or footer.get("total_received") or sum(int(row.get("received") or 0) for row in rows))
    outstanding = int(kpis.get("outstanding") or footer.get("outstanding") or sum(int(row.get("outstanding") or 0) for row in rows))
    return {
        "kind": "income_detail_report",
        "title": title,
        "total": total,
        "received": received,
        "outstanding": outstanding,
        "footer": {
            "total_transactions": int(footer.get("total_transactions") or len(rows)),
            "total_income": total,
            "total_received": received,
            "outstanding": outstanding,
        },
        "table": [("Date", "Voucher", "Customer", "Source", "Description", "Total", "Received", "Outstanding")] + [
            (
                row.get("date") or "-",
                row.get("voucher") or "-",
                row.get("customer") or "-",
                row.get("source") or "-",
                row.get("description") or "-",
                int(row.get("total") or 0),
                int(row.get("received") or 0),
                int(row.get("outstanding") or 0),
            )
            for row in rows
        ],
    }


def _chart_spec(result, question):
    formula = result.get("formula")
    forced = _forced_chart_type(question)
    bi_intent = result.get("_bi_intent") or {}
    report = bi_intent.get("report") or ""

    if formula == "expense_period_comparison":
        periods = result.get("periods") or []
        categories = result.get("categories") or []
        return {
            "kind": "expense_comparison_report",
            "title": result.get("_report_title") or "Expense Comparison",
            "periods": periods,
            "categories": categories,
            "ai_comment": result.get("ai_comment") or "",
            "values": [(row.get("label") or row.get("period") or "-", row.get("total_expense", 0)) for row in periods],
            "summary_table": [("Period", "Total Expense", "Received", "Outstanding", "Rows")] + [
                (
                    row.get("label") or row.get("period") or "-",
                    row.get("total_expense", 0),
                    row.get("received", 0),
                    row.get("outstanding", 0),
                    row.get("transaction_count", 0),
                )
                for row in periods
            ],
            "table": [("Category", "Previous", "Current", "Change", "Change %")] + [
                (
                    row.get("category") or "-",
                    row.get("previous_amount", 0),
                    row.get("current_amount", 0),
                    row.get("change", 0),
                    "-" if row.get("change_percent") is None else f"{row['change_percent']}%",
                )
                for row in categories
            ],
        }

    if formula == "master_name_comparison":
        rows = result.get("rows") or []
        totals = result.get("totals") or []
        chart_kind = "line" if len(totals) > 1 else "bar"
        return {
            "kind": "master_compare_report",
            "title": result.get("_report_title") or "Compare - Category Comparison",
            "chart_kind": chart_kind,
            "chart_title": "Compare Trend" if chart_kind == "line" else "Category Amounts",
            "total": result.get("total_amount", 0),
            "received": result.get("amount_received", 0),
            "outstanding": result.get("outstanding_amount", 0),
            "ai_comment": result.get("ai_comment") or "",
            "trend_values": [
                (row.get("period_bucket") or "-", row.get("amount", 0))
                for row in totals
            ],
            "values": [
                (
                    f"{row.get('period_bucket') or '-'} / {row.get('master_name') or '-'}",
                    row.get("amount", 0),
                )
                for row in rows
            ],
            "summary_table": [("Metric", "Amount"), ("Total", result.get("total_amount", 0)), ("Total Received", result.get("amount_received", 0)), ("Outstanding", result.get("outstanding_amount", 0)), ("Rows", result.get("row_count", 0))],
            "table": [("Bucket", "Category", "Sector", "Type", "Total", "Total Received", "Outstanding", "Rows")] + [
                (
                    row.get("period_bucket") or "-",
                    row.get("master_name") or "-",
                    row.get("sector") or "-",
                    row.get("income_expense") or "-",
                    row.get("amount", 0),
                    row.get("amount_received", 0),
                    row.get("outstanding_amount", 0),
                    row.get("row_count", 0),
                )
                for row in rows
            ],
        }

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

    if formula == "sales_total":
        spec = _financial_total_spec(result, bi_intent, "income")
        spec["income_rows"] = result.get("transection_income_rows") or []
        return spec

    if formula == "income_detail":
        return _income_detail_report_spec(result, bi_intent)

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
        if report == "income_summary":
            return _income_summary_rows(result, bi_intent)
        if report == "income_by_category":
            return _income_category_spec(result, bi_intent)
        if report in {"expense_summary", "income_by_category", "expense_by_category"}:
            return _financial_category_spec(result, bi_intent, report, amount_key)
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

    if formula == "expense_total":
        return _financial_total_spec(result, bi_intent, "expense")

    if formula == "sales_total" and bi_intent.get("business") == "farm":
        total_sales = int(result.get("total_sales") or 0)
        received = int(result.get("amount_received") or 0)
        outstanding = int(result.get("outstanding_amount") or 0)
        values = [("Received", received), ("Outstanding", outstanding)]
        if not any(value for _, value in values) and total_sales:
            values = [("Total Income", total_sales)]
        return {
            "kind": forced or "pie",
            "title": "Farm Total Income",
            "reason": "Best method: pie chart keeps total income simple by showing received versus outstanding amount.",
            "values": values,
            "table": [("Metric", "Amount"), ("Total Income", total_sales)] + values,
        }

    if formula in ("top_expenses", "top_income"):
        key = "expenses" if formula == "top_expenses" else "income"
        rows = result.get(key) or []
        if formula == "top_income" and report == "income_summary":
            return _income_summary_rows(result, bi_intent)
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
            "reason": "Best method: two-column voucher cards keep customer, voucher number, received amount, outstanding amount, and notes readable.",
            "vouchers": rows,
            "table": [("Voucher", "Customer", "Total", "Received", "Outstanding")] + [
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
            amount_name = "income" if bi_intent.get("module") == "income" else "expense"
            return _financial_detail_spec(result, bi_intent, amount_name)
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

    if (
        formula == "farm_transection_customer"
        and bi_intent.get("business") == "farm"
        and bi_intent.get("module") == "income"
        and report in {"income_detail", "income_transactions"}
    ):
        return _financial_detail_spec(result, bi_intent, "income")

    if (
        formula == "farm_transection_customer"
        and bi_intent.get("business") == "farm"
        and bi_intent.get("module") == "income"
    ):
        return _farm_financial_spec(result, question, bi_intent)

    if formula == "sotephwar_transection_summary":
        if report == "total_income":
            return _financial_total_spec(result, bi_intent, "income")
        return _income_summary_rows(result, bi_intent)

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

    if formula in {"sotephwar_product_ranking", "farm_product_ranking"}:
        if report in {"income_by_category", "sales_by_product", "top_products"}:
            return _income_category_spec(result, bi_intent)
        rows = result.get("products") or []
        return {
            "kind": forced or "bar",
            "title": "Product Ranking",
            "reason": "Best method: bar chart ranks products by revenue.",
            "values": [(row.get("product") or "-", row.get("total_amount", 0)) for row in rows],
            "table": [("Product", "Quantity", "Total", "Received", "Outstanding")] + [
                (
                    row.get("product") or "-",
                    row.get("quantity", 0),
                    row.get("total_amount", 0),
                    row.get("amount_received", 0),
                    row.get("outstanding_amount", 0),
                )
                for row in rows
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

    if formula == "sotephwar_inventory_value":
        rows = result.get("stock") or []
        return {
            "kind": forced or "stock_sheet",
            "title": "Sote Phwar Inventory Value",
            "reason": "Best method: stock sheet format shows current quantities, unit costs, and inventory values by store and product.",
            "stock": rows,
            "values": [(f"{row['store']} / {row['product']}", row.get("inventory_value", 0)) for row in rows],
            "table": [("Store", "Product", "Stock", "Unit Cost", "Inventory Value")] + [
                (
                    row["store"],
                    row["product"],
                    row.get("stock_qty", row.get("qty", 0)),
                    row.get("unit_cost", 0),
                    row.get("inventory_value", 0),
                )
                for row in rows
            ],
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


def _customer_revenue_spec(title, total_sales, total_received, total_outstanding, customers):
    customer_rows = sorted(
        customers or [],
        key=lambda row: int(row.get("total_amount") or row.get("amount") or 0),
        reverse=True,
    )
    if not customer_rows and int(total_sales or 0):
        customer_rows = [{
            "customer_name": "All Customers",
            "total_amount": total_sales,
            "amount_received": total_received,
            "outstanding_amount": total_outstanding,
        }]
    return {
        "kind": "customer_revenue_report",
        "title": title,
        "reason": "Best method: horizontal bars rank customers by revenue first, then grouped bars compare total sales, received amount, and outstanding amount.",
        "total_sales": total_sales,
        "total_received": total_received,
        "total_outstanding": total_outstanding,
        "customers": customer_rows,
        "values": [
            (row.get("customer_name") or row.get("item") or "-", row.get("total_amount", row.get("amount", 0)))
            for row in customer_rows[:12]
        ],
        "table": [("Customer Name", "Total Sales", "Received Amount", "Outstanding Amount")] + [
            (
                row.get("customer_name") or row.get("item") or "-",
                row.get("total_amount", row.get("amount", 0)),
                row.get("amount_received", 0),
                row.get("outstanding_amount", 0),
            )
            for row in customer_rows
        ],
    }


def _farm_customer_revenue_spec(result, title="Farm Customer Revenue Report"):
    customers = []
    for row in result.get("categories") or []:
        total_amount = int(row.get("income") or row.get("total_amount") or row.get("amount") or 0)
        if not total_amount:
            continue
        customers.append({
            "customer_name": row.get("customer_name") or row.get("category") or row.get("item") or "-",
            "total_amount": total_amount,
            "amount_received": int(row["amount_received"] if row.get("amount_received") is not None else total_amount),
            "outstanding_amount": int(row.get("outstanding_amount") or 0),
            "invoice_count": int(row.get("transaction_count") or row.get("invoice_count") or 0),
        })

    total_sales = int(result.get("total_income") or sum(row["total_amount"] for row in customers) or 0)
    total_received = sum(row["amount_received"] for row in customers)
    if not total_received and total_sales:
        total_received = total_sales
    total_outstanding = sum(row["outstanding_amount"] for row in customers)
    return _customer_revenue_spec(
        title,
        total_sales,
        total_received,
        total_outstanding,
        customers,
    )


def _voucher_table_spec(title, vouchers):
    normalized = []
    for row in vouchers or []:
        total = int(row.get("total_amount") or row.get("amount") or 0)
        if row.get("amount_received") is not None:
            received = int(row.get("amount_received") or 0)
        elif row.get("received") is not None:
            received = int(row.get("received") or 0)
        else:
            received = total
        if row.get("outstanding_amount") is not None:
            outstanding = int(row.get("outstanding_amount") or 0)
        else:
            outstanding = max(total - received, 0)
        normalized.append({
            "invoice_number": row.get("invoice_number") or row.get("voucher_number") or "-",
            "invoice_date": row.get("invoice_date") or row.get("Date") or row.get("date") or "-",
            "customer_name": row.get("customer_name") or row.get("customer") or row.get("item") or "-",
            "total_amount": total,
            "amount_received": received,
            "outstanding_amount": outstanding,
        })

    total = sum(row["total_amount"] for row in normalized)
    received = sum(row["amount_received"] for row in normalized)
    outstanding = sum(row["outstanding_amount"] for row in normalized)
    return {
        "kind": "voucher_table",
        "title": title,
        "reason": "Best method: table format keeps voucher number, date, customer, total, received, and outstanding readable.",
        "total": total,
        "received": received,
        "outstanding": outstanding,
        "vouchers": normalized,
        "table": [("Voucher Number", "Date", "Customer", "Total", "Received", "Outstanding")] + [
            (
                row["invoice_number"],
                row["invoice_date"],
                row["customer_name"],
                row["total_amount"],
                row["amount_received"],
                row["outstanding_amount"],
            )
            for row in normalized
        ],
    }


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
                    "amount_received": row["amount_received"] if row.get("amount_received") is not None else amount,
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
                "amount_received": row["amount_received"] if row.get("amount_received") is not None else amount if is_income else "",
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
                "amount_received": row["amount_received"] if row.get("amount_received") is not None else amount if is_income else "",
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


def _unicode_voucher_totals(vouchers):
    return {
        "count": len(vouchers),
        "total": sum(int(row.get("total_amount") or 0) for row in vouchers),
        "received": sum(int(row.get("amount_received") or 0) for row in vouchers),
        "outstanding": sum(int(row.get("outstanding_amount") or 0) for row in vouchers),
    }


def _unicode_voucher_report_header(title, question, report_title, totals):
    return [
        title,
        f"Question: {question}",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        report_title or "Vouchers",
        "",
        "SUMMARY",
        "-------",
        f"Total Vouchers : {_money(totals['count'])}",
        f"Total Amount   : {_money(totals['total'])} MMK",
        f"Total Received : {_money(totals['received'])} MMK",
        f"Outstanding    : {_money(totals['outstanding'])} MMK",
        "",
        "VOUCHERS",
        "--------",
    ]


def _unicode_voucher_block_lines(row, index, total_count):
    return [
        "=" * 64,
        f"Voucher {index} of {total_count} | No. {_unicode_value(row.get('invoice_number'))}",
        "-" * 64,
        f"Date        : {_unicode_value(row.get('invoice_date'))}",
        f"Customer    : {_unicode_value(row.get('customer_name'))}",
        f"Item        : {_unicode_value(row.get('item'))}",
        f"Quantity    : {_unicode_value(row.get('quantity'))}",
        "",
        "PAYMENT SUMMARY",
        f"Total       : {_money(row.get('total_amount') or 0)} MMK",
        f"Received    : {_money(row.get('amount_received') or 0)} MMK",
        f"Outstanding : {_money(row.get('outstanding_amount') or 0)} MMK",
        "",
        f"Note        : {_unicode_value(row.get('note'))}",
    ]


def _unicode_voucher_lines(title, question, spec):
    vouchers = spec.get("vouchers") or []
    totals = _unicode_voucher_totals(vouchers)
    lines = _unicode_voucher_report_header(title, question, spec.get("title") or "Vouchers", totals)
    if not vouchers:
        lines.append("No vouchers found.")
        return lines

    for index, row in enumerate(vouchers, start=1):
        lines.extend(_unicode_voucher_block_lines(row, index, totals["count"]))
        lines.append("")
    lines.append("=" * 64)
    return lines


def _unicode_voucher_table_lines(title, question, spec):
    vouchers = spec.get("vouchers") or []
    totals = _unicode_voucher_totals(vouchers)
    if spec.get("total") is not None:
        totals["total"] = int(spec.get("total") or 0)
    if spec.get("received") is not None:
        totals["received"] = int(spec.get("received") or 0)
    if spec.get("outstanding") is not None:
        totals["outstanding"] = int(spec.get("outstanding") or 0)
    lines = _unicode_voucher_report_header(title, question, spec.get("title") or "Income Detail", totals)
    if not vouchers:
        lines.append("No vouchers found.")
        return lines

    for index, row in enumerate(vouchers, start=1):
        lines.extend(_unicode_voucher_block_lines(row, index, totals["count"]))
        lines.append("")
    lines.append("=" * 64)
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


def _unicode_customer_revenue_lines(title, question, spec):
    lines = [
        title,
        f"Question: {question}",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        spec.get("title") or "Customer Revenue Report",
        "",
        "KPI Summary",
        f"Total Sales: {_money(spec.get('total_sales') or 0)}",
        f"Total Received: {_money(spec.get('total_received') or 0)}",
        f"Total Outstanding: {_money(spec.get('total_outstanding') or 0)}",
        "",
        "Top Customers by Revenue",
    ]
    customers = spec.get("customers") or []
    if not customers:
        lines.append("No customer sales found for this period.")
    for row in customers:
        lines.append(
            "{customer}: total {total}, received {received}, outstanding {outstanding}".format(
                customer=_unicode_value(row.get("customer_name") or row.get("item")),
                total=_money(row.get("total_amount", row.get("amount", 0))),
                received=_money(row.get("amount_received") or 0),
                outstanding=_money(row.get("outstanding_amount") or 0),
            )
        )
    lines.extend([
        "",
        "Customer Collection Status",
        "Customer Name | Total Sales | Received Amount | Outstanding Amount",
    ])
    for row in customers:
        lines.append(
            "{customer} | {total} | {received} | {outstanding}".format(
                customer=_unicode_value(row.get("customer_name") or row.get("item")),
                total=_money(row.get("total_amount", row.get("amount", 0))),
                received=_money(row.get("amount_received") or 0),
                outstanding=_money(row.get("outstanding_amount") or 0),
            )
        )
    return lines


def _unicode_transaction_ledger_lines(title, question, spec):
    lines = [
        spec.get("title") or title,
        "",
        f"Period: {spec.get('period_label') or '-'}",
    ]
    if spec.get("customer"):
        lines.append(f"Customer: {_unicode_value(spec.get('customer'))}")
    if spec.get("category"):
        lines.append(f"Category: {_unicode_value(spec.get('category'))}")
    lines.extend([
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
    ])

    transactions = spec.get("transactions") or []
    if not transactions:
        lines.append("No matching transactions found.")
    for row in transactions:
        description = _ledger_description(row)
        lines.extend([
            _display_date(row.get("date")),
            f"Amount: {_money(row.get('amount') or 0)} MMK",
            f"Payment: {_unicode_value(row.get('payment'))}",
            f"Description: {_unicode_value(description)}",
            "-" * 48,
            "",
        ])

    lines.extend([
        "Summary",
        f"Total Transactions: {len(transactions)}",
        f"Total Amount: {_money(spec.get('total') or 0)} MMK",
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
    if kind == "voucher_table":
        return _unicode_voucher_table_lines(title, question, spec)
    if kind == "farm_financial":
        return _unicode_farm_lines(title, question, spec)
    if kind == "customer_revenue_report":
        return _unicode_customer_revenue_lines(title, question, spec)
    if kind == "transaction_ledger_report":
        return _unicode_transaction_ledger_lines(title, question, spec)
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


def _bar_values(spec):
    return [(label, abs(int(value or 0))) for label, value in _spec_values(spec) if int(value or 0) != 0]


def _draw_bar_values(pdf, values, x=70, y=455, width=420, height=235, color_offset=0):
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
        pdf.rect(bar_x, yy + 2, drawn_width, max(8, row_height - 4), fill=PALETTE[(index + color_offset) % len(PALETTE)])
        pdf.text(value_x, yy + row_height - 5, _money(value), size=7.6, bold=True, max_width=value_width)


def _draw_bar(pdf, spec, x=70, y=455, width=420, height=235):
    _draw_bar_values(pdf, _bar_values(spec)[:12], x=x, y=y, width=width, height=height)


def _draw_bar_continuation_pages(pdf, spec, chart_title, start_index=12, page_size=22):
    values = _bar_values(spec)
    for offset in range(start_index, len(values), page_size):
        pdf.new_page()
        pdf.text(50, 795, f"{chart_title} (continued)", size=13, bold=True)
        _draw_bar_values(
            pdf,
            values[offset:offset + page_size],
            x=60,
            y=70,
            width=475,
            height=685,
            color_offset=offset,
        )


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


def _draw_income_summary_stacked_chart(pdf, rows, x=55, y=425, width=485, height=210, max_rows=8):
    chart_rows = rows[:max_rows]
    if not chart_rows:
        pdf.text(x, y + height / 2, "No income rows to chart.", size=11)
        return
    max_total = max(int(row.get("total_amount") or 0) for row in chart_rows) or 1
    label_width = 128
    value_width = 76
    bar_x = x + label_width + 10
    bar_width = width - label_width - value_width - 20
    value_x = bar_x + bar_width + 8
    row_gap = 9
    bar_height = max(13, min(21, (height - row_gap * (len(chart_rows) - 1)) / len(chart_rows)))
    paid_color = (39, 174, 96)
    outstanding_color = (235, 87, 87)

    pdf.line(bar_x, y, bar_x + bar_width, y, color=(190, 190, 190))
    for index, row in enumerate(chart_rows):
        yy = y + height - ((index + 1) * bar_height) - (index * row_gap)
        total = int(row.get("total_amount") or 0)
        paid = int(row.get("amount_received") or 0)
        outstanding = int(row.get("outstanding_amount") or 0)
        paid_width = bar_width * (paid / max_total)
        outstanding_width = bar_width * (outstanding / max_total)
        pdf.text(x, yy + bar_height - 4, row.get("customer") or "-", size=7.4, bold=True, max_width=label_width)
        if paid > 0:
            pdf.rect(bar_x, yy, max(1, paid_width), bar_height, fill=paid_color)
        if outstanding > 0:
            pdf.rect(bar_x + paid_width, yy, max(1, outstanding_width), bar_height, fill=outstanding_color)
        pdf.text(value_x, yy + bar_height - 5, _money(total), size=7.3, bold=True, max_width=value_width)

    legend_y = y - 24
    pdf.rect(x, legend_y, 10, 10, fill=paid_color)
    pdf.text(x + 14, legend_y + 1, "Paid / Total Received", size=8)
    pdf.rect(x + 140, legend_y, 10, 10, fill=outstanding_color)
    pdf.text(x + 154, legend_y + 1, "Outstanding Balance", size=8)


def _draw_income_summary_report(pdf, spec):
    pdf.text(50, 720, spec.get("title") or "Income Summary", size=13.5, bold=True)
    _draw_metric_cards(
        pdf,
        [
            ("Total Income", spec.get("total", 0)),
            ("Total Received", spec.get("received", 0)),
            ("Outstanding", spec.get("outstanding", 0)),
        ],
        y=692,
    )
    chart_title = spec.get("chart_title") or "Top Income by Customer"
    pdf.text(50, 620, chart_title, size=11.5, bold=True)
    _draw_income_summary_stacked_chart(pdf, spec.get("rows") or [], x=55, y=380, width=485, height=210)

    pdf.text(50, 332, "Data Table", size=12.5, bold=True)
    pdf.text(50, 314, spec.get("table_title") or "Income Summary Table", size=9.5, bold=True)
    _draw_table(
        pdf,
        spec.get("table"),
        start_y=292,
        column_widths=[48, 88, 50, 86, 72, 76, 75],
        font_size=6.6,
        line_gap=9,
        min_row_height=25,
    )


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


def _draw_line_chart(pdf, values, x=70, y=455, width=420, height=220):
    points = [(label, int(value or 0)) for label, value in values]
    if not points:
        pdf.text(x, y + height / 2, "No numeric values to chart.", size=11)
        return
    min_value = min(value for _, value in points)
    max_value = max(value for _, value in points)
    if min_value == max_value:
        padding = max(abs(max_value) * 0.1, 1)
        min_value -= padding
        max_value += padding
    value_range = max_value - min_value or 1

    def py_for(value):
        return y + ((value - min_value) / value_range) * height

    zero_y = py_for(0) if min_value <= 0 <= max_value else y
    pdf.line(x, zero_y, x + width, zero_y, color=(190, 190, 190))
    pdf.line(x, y, x, y + height, color=(190, 190, 190))
    pdf.line(x, y + height, x + width, y + height, color=(229, 231, 235))
    step = width / max(1, len(points) - 1)
    coordinates = []
    for index, (label, value) in enumerate(points):
        px = x + index * step
        py = py_for(value)
        coordinates.append((px, py, label, value))
    for index in range(1, len(coordinates)):
        previous = coordinates[index - 1]
        current = coordinates[index]
        pdf.line(previous[0], previous[1], current[0], current[1], color=(47, 128, 237), width=2)
    for px, py, label, value in coordinates:
        pdf.rect(px - 3, py - 3, 6, 6, fill=(47, 128, 237))
        pdf.text(px - 38, y - 18, label, size=8.2, bold=True, max_width=78)
        value_label_y = min(y + height - 10, max(y + 12, py + 18))
        pdf.text(px - 38, value_label_y, _money(value), size=8.2, bold=True, max_width=85)
    pdf.text(x + width - 78, y + height + 12, _money(max_value), size=7.4, color=(75, 85, 99))
    pdf.text(x + width - 78, y - 12, _money(min_value), size=7.4, color=(75, 85, 99))


def _draw_income_category_trend(pdf, rows, x=70, y=410, width=430, height=145):
    points = [
        (
            row.get("label") or "-",
            int(row.get("received") or 0),
            int(row.get("outstanding") or 0),
        )
        for row in rows
    ]
    if not points:
        pdf.text(x, y + height / 2, "No monthly values to chart.", size=11)
        return
    all_values = [value for _, received, outstanding in points for value in (received, outstanding)]
    min_value = min(0, min(all_values))
    max_value = max(all_values) if all_values else 1
    if min_value == max_value:
        max_value += 1
    value_range = max_value - min_value or 1

    def py_for(value):
        return y + ((value - min_value) / value_range) * height

    step = width / max(1, len(points) - 1)
    pdf.line(x, y, x, y + height, color=(190, 190, 190))
    pdf.line(x, y, x + width, y, color=(190, 190, 190))
    pdf.line(x, y + height, x + width, y + height, color=(229, 231, 235))
    series = [
        ("Total Received", 1, (39, 174, 96)),
        ("Outstanding Balance", 2, (235, 87, 87)),
    ]
    for label, value_index, color in series:
        coords = []
        for index, point in enumerate(points):
            px = x + index * step
            py = py_for(point[value_index])
            coords.append((px, py, point[0], point[value_index]))
        for index in range(1, len(coords)):
            previous = coords[index - 1]
            current = coords[index]
            pdf.line(previous[0], previous[1], current[0], current[1], color=color, width=2)
        for px, py, _, _ in coords:
            pdf.rect(px - 2.5, py - 2.5, 5, 5, fill=color)

    for index, (label, received, outstanding) in enumerate(points):
        px = x + index * step
        pdf.text(px - 34, y - 18, label, size=7.6, bold=True, max_width=72)
        top_value = max(received, outstanding)
        pdf.text(px - 34, min(y + height - 8, py_for(top_value) + 13), _money(top_value), size=7.2, bold=True, max_width=78)
    pdf.text(x + width - 82, y + height + 12, _money(max_value), size=7.4, color=(75, 85, 99))
    pdf.text(x + width - 82, y - 12, _money(min_value), size=7.4, color=(75, 85, 99))

    legend_y = y + height + 28
    legend_x = x
    for label, _, color in series:
        pdf.rect(legend_x, legend_y, 10, 10, fill=color)
        pdf.text(legend_x + 14, legend_y + 1, label, size=8)
        legend_x += 150


def _draw_table(pdf, table, start_y=365, column_widths=None, font_size=8.1, line_gap=11, min_row_height=22):
    if not table:
        return start_y
    y = start_y
    col_count = max(len(row) for row in table)
    if column_widths and len(column_widths) == col_count:
        widths = column_widths
    else:
        widths = [495 / col_count] * col_count
    header = table[0]
    x_positions = [54]
    for width in widths[:-1]:
        x_positions.append(x_positions[-1] + width)

    def draw_row(row, row_index, y):
        wrapped = []
        line_count = 1
        for col_index, cell in enumerate(row):
            text = _money(cell) if isinstance(cell, (int, float)) else str(cell)
            lines = _wrap_pdf_text(text, widths[col_index] - 8, font_size)
            wrapped.append(lines)
            line_count = max(line_count, len(lines))
        row_height = max(min_row_height, 12 + line_count * line_gap)
        fill = (219, 226, 235) if row_index == 0 else ((244, 247, 251) if row_index % 2 == 0 else None)
        if fill:
            pdf.rect(50, y - row_height + 9, 495, row_height, fill=fill)
        for col_index, lines in enumerate(wrapped):
            for line_index, line in enumerate(lines):
                pdf.text(
                    x_positions[col_index],
                    y - (line_index * line_gap),
                    line,
                    size=font_size,
                    bold=True,
                    max_width=widths[col_index] - 8,
                )
        return y - row_height, row_height

    for row_index, row in enumerate(table):
        wrapped_line_count = 1
        for col_index, cell in enumerate(row):
            text = _money(cell) if isinstance(cell, (int, float)) else str(cell)
            wrapped_line_count = max(wrapped_line_count, len(_wrap_pdf_text(text, widths[col_index] - 8, font_size)))
        row_height = max(min_row_height, 12 + wrapped_line_count * line_gap)
        if y - row_height < 45:
            pdf.new_page()
            y = 785
            if row_index:
                y, _ = draw_row(header, 0, y)
        y, _ = draw_row(row, row_index, y)
    return y


def _draw_metric_cards(pdf, metrics, x=50, y=680, cell_width=165, cell_height=46):
    fills = [
        (242, 246, 251),
        (226, 242, 233),
        (249, 233, 233),
    ]
    for index, (label, value) in enumerate(metrics):
        cell_x = x + (cell_width * index)
        pdf.rect(cell_x, y - cell_height, cell_width, cell_height, fill=fills[index % len(fills)], stroke=(180, 190, 204))
        pdf.text(cell_x + 10, y - 16, label, size=8.8, bold=True, color=(75, 85, 99))
        pdf.text(cell_x + 10, y - 36, _money(value), size=13.2, bold=True, max_width=cell_width - 20)


def _draw_financial_total_report(pdf, spec):
    pdf.text(50, 720, spec["title"], size=13.5, bold=True)
    metrics = [(spec.get("amount_label") or "Total", spec.get("total", 0))]
    if spec.get("show_collection", True):
        metrics.extend([
            ("Received", spec.get("received", 0)),
            ("Outstanding", spec.get("outstanding", 0)),
        ])
    else:
        metrics.extend([
            ("Rows", spec.get("row_count", 0)),
            ("Monthly Points", len(spec.get("trend_values") or [])),
        ])
    _draw_metric_cards(pdf, metrics, y=692)
    pdf.text(50, 610, spec.get("trend_title") or "Monthly Trend", size=11.5, bold=True)
    _draw_line_chart(pdf, spec.get("trend_values") or [], x=70, y=410, width=430, height=145)

    if spec.get("show_collection", True):
        pdf.text(50, 360, "Received vs Outstanding", size=11.5, bold=True)
        _draw_pie(pdf, spec, cx=185, cy=235, radius=68)

        pdf.text(320, 360, "Collection Status Bar", size=11.5, bold=True)
        _draw_bar_values(
            pdf,
            spec.get("values") or [],
            x=315,
            y=160,
            width=225,
            height=155,
        )
    else:
        pdf.text(50, 360, "Expense Movement", size=11.5, bold=True)
        pdf.text(
            50,
            332,
            "Expense reports show spending only, not customer collection balances.",
            size=9.2,
            max_width=495,
            color=(75, 85, 99),
        )

    pdf.new_page()
    pdf.text(50, 795, "Necessary Table", size=13, bold=True)
    _draw_table(pdf, spec.get("table"), start_y=762)
    y = 610
    pdf.text(50, y, "Management Note", size=12, bold=True)
    y -= 24
    if spec.get("show_collection", True):
        outstanding = int(spec.get("outstanding") or 0)
        total = int(spec.get("total") or 0)
        outstanding_share = round((outstanding / total) * 100, 1) if total else 0
        notes = [
            f"Outstanding represents {outstanding_share}% of the selected total.",
            "Use the trend line to check whether the current period is normal or an unusual movement.",
            "If the latest month is materially different from the prior trend, management should check the source category, customer, or payment timing before making spending decisions.",
        ]
    else:
        notes = [
            "Use the trend line to check whether the selected expense period is normal or unusual.",
            "If the latest month is materially different from the prior trend, management should check the source category and spending timing before making spending decisions.",
        ]
    for note in notes:
        y -= pdf.text(50, y, f"- {note}", size=9.2, max_width=495)


def _draw_income_category_report(pdf, spec):
    pdf.text(50, 720, spec.get("title") or "Income by Category", size=13.5, bold=True)
    _draw_metric_cards(
        pdf,
        [
            ("Total Income", spec.get("total", 0)),
            ("Total Received", spec.get("received", 0)),
            ("Outstanding Balance", spec.get("outstanding", 0)),
        ],
        y=692,
    )
    pdf.text(50, 610, "Monthly Collection Trend", size=11.5, bold=True)
    _draw_income_category_trend(pdf, spec.get("trend_rows") or [], x=70, y=405, width=430, height=145)

    pdf.text(50, 350, "Category/Product Table", size=12.5, bold=True)
    _draw_table(
        pdf,
        spec.get("table"),
        start_y=322,
        column_widths=[118, 50, 80, 84, 92, 71],
        font_size=6.9,
        line_gap=9,
        min_row_height=24,
    )


def _draw_income_detail_report(pdf, spec):
    pdf.text(50, 720, spec.get("title") or "Income Detail", size=13.5, bold=True)
    _draw_metric_cards(
        pdf,
        [
            ("Total Income", spec.get("total", 0)),
            ("Total Received", spec.get("received", 0)),
            ("Outstanding", spec.get("outstanding", 0)),
        ],
        y=692,
    )
    pdf.text(50, 610, "Transaction Detail", size=12.5, bold=True)
    y = _draw_table(
        pdf,
        spec.get("table"),
        start_y=582,
        column_widths=[48, 42, 68, 112, 75, 50, 50, 50],
        font_size=6.2,
        line_gap=8,
        min_row_height=24,
    )
    if y < 145:
        pdf.new_page()
        y = 785
    footer = spec.get("footer") or {}
    pdf.text(50, y - 22, "Footer Summary", size=11.5, bold=True)
    summary_rows = [
        ("Total Transactions", footer.get("total_transactions", 0)),
        ("Total Income", footer.get("total_income", 0)),
        ("Total Received", footer.get("total_received", 0)),
        ("Outstanding", footer.get("outstanding", 0)),
    ]
    _draw_table(
        pdf,
        [("Metric", "Amount")] + summary_rows,
        start_y=y - 50,
        column_widths=[260, 235],
        font_size=8,
        line_gap=10,
        min_row_height=22,
    )


def _draw_financial_category_report(pdf, spec):
    pdf.text(50, 720, spec["title"], size=12, bold=True)
    metrics = [(spec.get("amount_label") or "Total", spec.get("total", 0))]
    if spec.get("show_collection", True):
        metrics.extend([
            ("Received", spec.get("received", 0)),
            ("Outstanding", spec.get("outstanding", 0)),
        ])
    else:
        metrics.extend([
            ("Categories", spec.get("category_count", 0)),
            ("Rows", spec.get("row_count", 0)),
        ])
    _draw_metric_cards(pdf, metrics, y=692)

    chart_title = spec.get("chart_title") or "Categories"
    pdf.text(50, 610, chart_title, size=11.5, bold=True)
    _draw_bar(pdf, spec, x=60, y=110, width=475, height=465)
    _draw_bar_continuation_pages(pdf, spec, chart_title)

    pdf.new_page()
    pdf.text(50, 795, "Data Table", size=13, bold=True)
    pdf.text(50, 773, spec.get("table_title") or "Category Table", size=10.5, bold=True)
    _draw_table(pdf, spec.get("table"), start_y=742)


def _draw_financial_detail_report(pdf, spec):
    pdf.text(50, 720, spec["title"], size=12, bold=True)
    _draw_metric_cards(
        pdf,
        [
            (spec.get("amount_label") or "Total", spec.get("total", 0)),
            ("Received", spec.get("received", 0)),
            ("Outstanding", spec.get("outstanding", 0)),
        ],
        y=692,
    )

    chart_title = spec.get("chart_title") or "Detail"
    pdf.text(50, 610, chart_title, size=11.5, bold=True)
    _draw_bar(pdf, spec, x=60, y=110, width=475, height=465)
    _draw_bar_continuation_pages(pdf, spec, chart_title)

    pdf.new_page()
    pdf.text(50, 795, "Data Table", size=13, bold=True)
    pdf.text(50, 773, spec.get("table_title") or "Detail Table", size=10.5, bold=True)
    _draw_table(
        pdf,
        spec.get("table"),
        start_y=742,
        column_widths=[60, 130, 125, 55, 58, 50, 67],
        font_size=7.4,
        line_gap=12,
        min_row_height=28,
    )


def _draw_transaction_ledger_report(pdf, spec):
    pdf.text(50, 720, spec["title"], size=15, bold=True)
    y = 690
    pdf.text(50, y, f"Period: {spec.get('period_label') or '-'}", size=9.5, bold=True)
    y -= 18
    if spec.get("customer"):
        pdf.text(50, y, f"Customer: {spec.get('customer')}", size=9.5, bold=True, max_width=495)
        y -= 18
    if spec.get("category"):
        pdf.text(50, y, f"Category: {spec.get('category')}", size=9.5, bold=True, max_width=495)
        y -= 18

    pdf.line(50, y - 4, 545, y - 4, color=(209, 213, 219))
    y -= 34
    transactions = spec.get("transactions") or []
    if not transactions:
        pdf.text(50, y, "No matching transactions found.", size=10)
        y -= 26

    for row in transactions:
        if y < 145:
            pdf.new_page()
            pdf.text(50, 795, spec["title"], size=14, bold=True)
            y = 755
        description = _ledger_description(row)
        pdf.text(50, y, _display_date(row.get("date")), size=10.5, bold=True)
        pdf.text(360, y, "Amount:", size=9.2, bold=True, color=(75, 85, 99))
        pdf.text(420, y, _mmk(row.get("amount") or 0), size=9.2, bold=True, max_width=120)
        y -= 18
        pdf.text(50, y, f"Payment: {row.get('payment') or '-'}", size=9.2, max_width=230)
        y -= 18
        pdf.text(50, y, "Description:", size=9.2, bold=True, color=(75, 85, 99))
        used = pdf.text(135, y, description, size=9.2, max_width=400)
        y -= max(22, used + 8)
        pdf.line(50, y, 545, y, color=(229, 231, 235))
        y -= 24

    if y < 120:
        pdf.new_page()
        y = 760
    pdf.text(50, y, "Summary", size=11, bold=True)
    y -= 22
    pdf.text(50, y, f"Total Transactions: {len(transactions)}", size=9.7, bold=True)
    y -= 20
    pdf.text(50, y, f"Total Amount: {_mmk(spec.get('total') or 0)}", size=9.7, bold=True)


def _draw_expense_comparison_report(pdf, spec):
    pdf.text(50, 720, spec["title"], size=12, bold=True)
    periods = spec.get("periods") or []
    if periods:
        metrics = [
            (row.get("label") or row.get("period") or "-", row.get("total_expense", 0))
            for row in periods[:3]
        ]
        _draw_metric_cards(pdf, metrics, y=692, cell_width=165)

    pdf.text(50, 610, "Expense Comparison Trend", size=11.5, bold=True)
    _draw_line_chart(pdf, spec.get("values") or [], x=70, y=365, width=430, height=190)

    pdf.text(50, 320, "Period Summary", size=11.5, bold=True)
    _draw_table(pdf, spec.get("summary_table"), start_y=296)

    pdf.new_page()
    pdf.text(50, 795, "Local AI Comment", size=13, bold=True)
    y = 770
    for paragraph in (spec.get("ai_comment") or "-").splitlines():
        if not paragraph:
            y -= 8
            continue
        y -= pdf.text(50, y, paragraph, size=9.2, max_width=495)
        if y < 80:
            pdf.new_page()
            y = 795

    pdf.new_page()
    pdf.text(50, 795, "Category Comparison Table", size=13, bold=True)
    _draw_table(pdf, spec.get("table"), start_y=760)


def _draw_master_compare_report(pdf, spec):
    pdf.text(50, 720, spec["title"], size=12, bold=True)
    _draw_metric_cards(
        pdf,
        [
            ("Total", spec.get("total", 0)),
            ("Total Received", spec.get("received", 0)),
            ("Outstanding", spec.get("outstanding", 0)),
        ],
        y=692,
    )

    chart_kind = spec.get("chart_kind")
    pdf.text(50, 610, spec.get("chart_title") or "Compare Chart", size=11.5, bold=True)
    if chart_kind == "line":
        _draw_line_chart(pdf, spec.get("trend_values") or [], x=70, y=365, width=430, height=190)
        summary_y = 320
        table_y = 296
    else:
        _draw_bar(pdf, spec, x=60, y=260, width=475, height=290)
        summary_y = 220
        table_y = 196

    pdf.text(50, summary_y, "Summary", size=11.5, bold=True)
    _draw_table(
        pdf,
        spec.get("summary_table"),
        start_y=table_y,
        column_widths=[245, 250],
    )

    pdf.new_page()
    pdf.text(50, 795, "Compare Table", size=13, bold=True)
    _draw_table(
        pdf,
        spec.get("table"),
        start_y=760,
        column_widths=[62, 125, 70, 58, 62, 62, 78, 38],
        font_size=7.1,
        line_gap=10,
        min_row_height=24,
    )

    pdf.new_page()
    pdf.text(50, 795, "Local AI Comment", size=13, bold=True)
    y = 770
    for paragraph in (spec.get("ai_comment") or "-").splitlines():
        if not paragraph:
            y -= 8
            continue
        y -= pdf.text(50, y, paragraph, size=9.2, max_width=495)
        if y < 80:
            pdf.new_page()
            y = 795


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
        ("Received", sum(int(row.get("amount_received") or 0) for row in vouchers)),
        ("Outstanding", sum(int(row.get("outstanding_amount") or 0) for row in vouchers)),
    ]
    cell_width = 165
    cell_height = 42
    for index, (label, value) in enumerate(totals):
        cell_x = x + (cell_width * index)
        pdf.rect(cell_x, y - cell_height, cell_width, cell_height, fill=(246, 248, 251), stroke=(130, 145, 166))
        pdf.text(cell_x + 10, y - 15, label, size=8.8, bold=True, color=(75, 85, 99))
        pdf.text(cell_x + 10, y - 33, _money(value), size=13, bold=True)


def _draw_voucher_table(pdf, vouchers, start_y=620):
    headers = ("Voucher Number", "Date", "Customer", "Total", "Received", "Outstanding")
    column_width = 495 / len(headers)
    widths = [column_width] * len(headers)
    x_positions = [54 + (index * column_width) for index in range(len(headers))]
    y = start_y
    font_size = 6.3
    line_gap = 9

    def draw_header(current_y):
        pdf.rect(50, current_y - 7, 495, 25, fill=(219, 226, 235))
        for index, header in enumerate(headers):
            pdf.text(x_positions[index], current_y, header, size=font_size, bold=True, max_width=widths[index] - 10)

    draw_header(y)
    y -= 30
    if not vouchers:
        pdf.text(58, y, "No vouchers found.", size=9)
        return

    for index, row in enumerate(vouchers):
        if y < 58:
            pdf.new_page()
            pdf.text(50, 795, "Income Detail", size=16, bold=True)
            y = 755
            draw_header(y)
            y -= 30

        values = (
            f"Voucher {row.get('invoice_number') or '-'}",
            row.get("invoice_date") or "-",
            row.get("customer_name") or "-",
            _money(row.get("total_amount") or 0),
            _money(row.get("amount_received") or 0),
            _money(row.get("outstanding_amount") or 0),
        )
        wrapped_cells = [
            _wrap_pdf_text(value, widths[col_index] - 10, font_size)
            for col_index, value in enumerate(values)
        ]
        line_count = max(len(lines) for lines in wrapped_cells)
        row_height = max(30, 15 + (line_count * line_gap))
        if index % 2 == 0:
            pdf.rect(50, y - row_height + 10, 495, row_height, fill=(246, 248, 251))

        for col_index, lines in enumerate(wrapped_cells):
            for line_index, line in enumerate(lines):
                pdf.text(
                    x_positions[col_index],
                    y - (line_index * line_gap),
                    line,
                    size=font_size,
                    bold=True,
                    max_width=widths[col_index] - 10,
                )
        y -= row_height


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


def _draw_stock_sheet_header(pdf, y, has_value=False):
    pdf.rect(50, y - 6, 495, 24, fill=(218, 226, 236))
    pdf.text(58, y, "Store", size=8.8, bold=True)
    pdf.text(172, y, "Product", size=8.8, bold=True)
    pdf.text(330, y, "Qty", size=8.8, bold=True)
    if has_value:
        pdf.text(386, y, "Unit Cost", size=8.8, bold=True)
        pdf.text(462, y, "Value", size=8.8, bold=True)
    else:
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
            "unit_cost": int(row.get("unit_cost") or 0),
            "inventory_value": int(row.get("inventory_value") or 0),
        }
        for row in rows
    ]
    total_qty = sum(row["quantity"] for row in normalized)
    total_value = sum(row["inventory_value"] for row in normalized)
    has_value = any(row["unit_cost"] or row["inventory_value"] for row in normalized)
    low_count = sum(1 for row in normalized if 0 < row["quantity"] <= 10)
    out_count = sum(1 for row in normalized if row["quantity"] <= 0)

    pdf.text(50, start_y, "Stock Summary", size=11.5, bold=True)
    summary_y = start_y - 18
    _draw_stock_summary_box(pdf, 50, summary_y, "Total SKUs", len(normalized), (242, 246, 251))
    _draw_stock_summary_box(pdf, 178, summary_y, "Total Qty", total_qty, (239, 247, 243))
    _draw_stock_summary_box(pdf, 306, summary_y, "Inventory Value" if has_value else "Low Stock", total_value if has_value else low_count, (255, 248, 229))
    _draw_stock_summary_box(pdf, 433, summary_y, "Low Stock" if has_value else "Out of Stock", low_count if has_value else out_count, (249, 233, 233))

    y = start_y - 92
    _draw_stock_sheet_header(pdf, y, has_value=has_value)
    y -= 28
    row_height = 24

    for index, row in enumerate(normalized):
        if y < 65:
            pdf.new_page()
            pdf.text(50, 795, "Sote Phwar Inventory Stock", size=16, bold=True)
            y = 755
            _draw_stock_sheet_header(pdf, y, has_value=has_value)
            y -= 28

        fill = (246, 248, 251) if index % 2 == 0 else None
        if fill:
            pdf.rect(50, y - 7, 495, row_height, fill=fill)

        status, badge_fill, badge_text = _stock_status(row["quantity"])
        pdf.text(58, y, _short_label(row["store"], 24), size=8.4, bold=True, max_width=126)
        pdf.text(172, y, _short_label(row["product"], 32), size=8.4, bold=True, max_width=150)
        pdf.text(330, y, _money(row["quantity"]), size=8.8, bold=True, max_width=48)
        if has_value:
            pdf.text(386, y, _money(row["unit_cost"]), size=8.4, bold=True, max_width=70)
            pdf.text(462, y, _money(row["inventory_value"]), size=8.4, bold=True, max_width=72)
        else:
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
    if spec.get("is_income"):
        paid = sum(int(row.get("amount_received") or 0) for row in spec.get("rows") or [])
        outstanding = sum(int(row.get("outstanding_amount") or 0) for row in spec.get("rows") or [])
        _draw_farm_metric_box(pdf, 50, start_y - 65, "Total", spec.get("total", 0), total_fill)
        _draw_farm_metric_box(pdf, 220, start_y - 65, "Paid", paid, (226, 242, 233))
        _draw_farm_metric_box(pdf, 390, start_y - 65, "Outstanding", outstanding, (249, 233, 233))
    else:
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


def _draw_customer_metric_card(pdf, x, y, label, value, fill):
    pdf.rect(x, y - 50, 155, 50, fill=fill, stroke=(180, 190, 204))
    pdf.text(x + 10, y - 17, label, size=8.7, bold=True, color=(75, 85, 99))
    pdf.text(x + 10, y - 38, _money(value), size=14.3, bold=True)


def _draw_customer_detail_table(pdf, rows, start_y=760):
    headers = ("Customer Name", "Total Sales", "Received Amount", "Outstanding Amount")
    widths = (205, 96, 96, 98)
    x_positions = (54, 259, 355, 451)
    y = start_y

    def draw_header(current_y):
        pdf.rect(50, current_y - 7, 495, 25, fill=(219, 226, 235))
        for index, header in enumerate(headers):
            pdf.text(x_positions[index], current_y, header, size=8.3, bold=True, max_width=widths[index] - 8)

    pdf.text(50, y + 30, "Customer Detail Table", size=12, bold=True)
    draw_header(y)
    y -= 30
    if not rows:
        pdf.text(58, y, "No customer sales found for this period.", size=9)
        return

    for index, row in enumerate(rows):
        if y < 62:
            pdf.new_page()
            pdf.text(50, 795, "Customer Detail Table", size=16, bold=True)
            y = 755
            draw_header(y)
            y -= 30

        customer = row.get("customer_name") or row.get("item") or "-"
        customer_lines = _wrap_pdf_text(customer, widths[0] - 8, 8.2)
        row_height = max(24, 13 + (len(customer_lines) * 11))
        if index % 2 == 0:
            pdf.rect(50, y - row_height + 10, 495, row_height, fill=(246, 248, 251))
        for line_index, line in enumerate(customer_lines):
            pdf.text(x_positions[0], y - (line_index * 11), line, size=8.2, bold=True, max_width=widths[0] - 8)
        pdf.text(x_positions[1], y, _money(row.get("total_amount", row.get("amount", 0))), size=8.2, bold=True, max_width=widths[1] - 8)
        pdf.text(x_positions[2], y, _money(row.get("amount_received") or 0), size=8.2, bold=True, max_width=widths[2] - 8)
        pdf.text(x_positions[3], y, _money(row.get("outstanding_amount") or 0), size=8.2, bold=True, max_width=widths[3] - 8)
        y -= row_height


def _draw_customer_collection_grouped_bars(pdf, rows, x=60, y=278, width=475, height=118):
    rows = rows[:6]
    if not rows:
        pdf.text(x, y + height / 2, "No customer sales found for this period.", size=10)
        return

    max_value = max(
        max(
            int(row.get("total_amount", row.get("amount", 0)) or 0),
            int(row.get("amount_received") or 0),
            int(row.get("outstanding_amount") or 0),
        )
        for row in rows
    ) or 1
    label_width = 130
    bar_x = x + label_width + 10
    bar_width = width - label_width - 95
    group_gap = 7
    bar_height = 5
    group_height = max(16, min(28, (height - group_gap * (len(rows) - 1)) / len(rows)))
    series = [
        ("Sales", "total_amount", (47, 128, 237)),
        ("Received", "amount_received", (39, 174, 96)),
        ("Outstanding", "outstanding_amount", (235, 87, 87)),
    ]

    for index, row in enumerate(rows):
        yy = y + height - ((index + 1) * group_height) - (index * group_gap)
        pdf.text(x, yy + group_height - 4, _short_label(row.get("customer_name") or row.get("item") or "-", 22), size=7.4, bold=True, max_width=label_width)
        for s_index, (_, key, color) in enumerate(series):
            value = int(row.get(key, row.get("amount", 0) if key == "total_amount" else 0) or 0)
            bar_y = yy + group_height - 8 - (s_index * (bar_height + 1))
            pdf.rect(bar_x, bar_y, max(1, bar_width * (value / max_value)), bar_height, fill=color)
        pdf.text(bar_x + bar_width + 8, yy + group_height - 9, _money(row.get("outstanding_amount") or 0), size=7.2, bold=True, max_width=70)

    legend_x = x
    for label, _, color in series:
        pdf.rect(legend_x, y - 22, 9, 9, fill=color)
        pdf.text(legend_x + 13, y - 21, label, size=7.8)
        legend_x += 78
    pdf.text(bar_x + bar_width + 8, y - 21, "Right value: outstanding", size=7.5, color=(75, 85, 99))


def _draw_customer_revenue_bar_page(pdf, rows, max_value, x=60, y=80, width=475, height=480):
    if not rows:
        pdf.text(x, y + height / 2, "No customer sales found for this period.", size=10)
        return

    label_width = 165
    value_width = 82
    bar_x = x + label_width + 12
    bar_width = max(90, width - label_width - value_width - 26)
    value_x = bar_x + bar_width + 10
    row_gap = 5
    row_height = max(16, min(23, (height - row_gap * (len(rows) - 1)) / len(rows)))
    pdf.line(bar_x, y, bar_x + bar_width, y, color=(190, 190, 190))

    for index, row in enumerate(rows):
        label = row.get("customer_name") or row.get("item") or "-"
        value = abs(int(row.get("total_amount", row.get("amount", 0)) or 0))
        yy = y + height - ((index + 1) * row_height) - (index * row_gap)
        drawn_width = max(1, bar_width * (value / (max_value or 1)))
        pdf.text(x, yy + row_height - 4, _short_label(label, 30), size=7.2, bold=True, max_width=label_width)
        pdf.rect(bar_x, yy + 2, drawn_width, max(8, row_height - 4), fill=PALETTE[index % len(PALETTE)])
        pdf.text(value_x, yy + row_height - 5, _money(value), size=7.3, bold=True, max_width=value_width)


def _draw_customer_revenue_report(pdf, spec, start_y=720):
    customers = spec.get("customers") or []
    pdf.text(50, start_y, spec["title"], size=13, bold=True)

    pdf.text(50, start_y - 28, "KPI Summary", size=11.2, bold=True)
    metric_y = start_y - 48
    _draw_customer_metric_card(pdf, 50, metric_y, "Total Sales", spec.get("total_sales", 0), (230, 239, 251))
    _draw_customer_metric_card(pdf, 220, metric_y, "Total Received", spec.get("total_received", 0), (226, 242, 233))
    _draw_customer_metric_card(pdf, 390, metric_y, "Total Outstanding", spec.get("total_outstanding", 0), (249, 233, 233))

    pdf.text(50, start_y - 120, "Top Customers by Revenue", size=11.2, bold=True)
    max_sales = max((int(row.get("total_amount", row.get("amount", 0)) or 0) for row in customers), default=1)
    first_page_count = 14
    continued_page_count = 24
    _draw_customer_revenue_bar_page(
        pdf,
        customers[:first_page_count],
        max_sales,
        x=60,
        y=82,
        width=475,
        height=start_y - 225,
    )

    offset = first_page_count
    while offset < len(customers):
        pdf.new_page()
        pdf.text(50, 795, "Top Customers by Revenue (continued)", size=13, bold=True)
        _draw_customer_revenue_bar_page(
            pdf,
            customers[offset:offset + continued_page_count],
            max_sales,
            x=60,
            y=82,
            width=475,
            height=665,
        )
        offset += continued_page_count

    pdf.new_page()
    pdf.text(50, 795, "Customer Collection Status", size=13, bold=True)
    _draw_customer_collection_grouped_bars(pdf, customers, x=60, y=560, width=475, height=165)

    pdf.new_page()
    _draw_customer_detail_table(pdf, customers, start_y=760)


def _is_ceo_management_report_question(question):
    text = " ".join(str(question).lower().split())
    is_report = "pdf" in text or "report" in text
    is_kpi_management_report = (
        "kpi" in text
        and (
            "pdf" in text
            or "report" in text
            or "management" in text
            or "dashboard" in text
        )
    )
    explicit_ceo_report = (
        "ceo" in text
        or "chief executive" in text
        or "management report" in text
        or "monthly management report" in text
    )
    local_ai_ceo_alias = (
        is_report
        and ("local ai" in text or "qwen" in text or "qwen3" in text)
        and ("finance" in text or "business" in text)
    )
    return is_report and (explicit_ceo_report or local_ai_ceo_alias or is_kpi_management_report)


def _safe_call(func, *args, default=None, **kwargs):
    try:
        return func(*args, **kwargs)
    except Exception:
        return default if default is not None else {}


def _ceo_report_period(question, fallback_period):
    period = normalize_period(question)
    return fallback_period if period == "all_time" else period


def _ceo_period_label(period, fallback_label):
    year_match = re.fullmatch(r"year:(\d{4})", period)
    if year_match:
        return year_match.group(1)
    month_match = re.fullmatch(r"month:(\d{4})-(\d{2})", period)
    if month_match:
        return date(int(month_match.group(1)), int(month_match.group(2)), 1).strftime("%B %Y")
    date_match = re.fullmatch(r"date:(\d{4})-(\d{2})-(\d{2})", period)
    if date_match:
        return date(
            int(date_match.group(1)),
            int(date_match.group(2)),
            int(date_match.group(3)),
        ).strftime("%d %B %Y").lstrip("0")
    labels = {
        "today": "today",
        "yesterday": "yesterday",
        "this_week": "this week",
        "last_week": "last week",
        "this_month": "this month",
        "last_month": "last month",
        "this_year": str(date.today().year),
        "last_year": str(date.today().year - 1),
    }
    return labels.get(period, fallback_label)


def _ceo_previous_period(period):
    year_match = re.fullmatch(r"year:(\d{4})", period)
    if year_match:
        return f"year:{int(year_match.group(1)) - 1}"
    month_match = re.fullmatch(r"month:(\d{4})-(\d{2})", period)
    if month_match:
        year = int(month_match.group(1))
        month = int(month_match.group(2))
        if month == 1:
            return f"month:{year - 1}-12"
        return f"month:{year}-{month - 1:02d}"
    return {
        "this_year": "last_year",
        "this_month": "last_month",
        "this_week": "last_week",
    }.get(period)


def _business_unit_for_sector(sector):
    if sector in {"Sote Phwar", "SP Extension", "SP Production"}:
        return "Sote Phwar"
    if sector == "Farm":
        return "Farm"
    return None


def _expense_category_label(sector, category):
    group = _business_unit_for_sector(sector)
    if group == "Sote Phwar" and sector == "SP Extension":
        return f"Sote Phwar / Extension / {category or '-'}"
    if group == "Sote Phwar" and sector == "SP Production":
        return f"Sote Phwar / Production / {category or '-'}"
    if group:
        return f"{group} / {category or '-'}"
    return category or "-"


def _ceo_business_units(sectors):
    units = {
        "Sote Phwar": {"revenue": 0, "profit": 0},
        "Farm": {"revenue": 0, "profit": 0},
    }
    for row in sectors:
        key = _business_unit_for_sector(row.get("sector") or "")
        if not key:
            continue
        units[key]["revenue"] += int(row.get("income") or 0)
        units[key]["profit"] += int(row.get("profit") or 0)
    return units


def _ceo_expense_categories(categories):
    grouped = {}
    for row in categories:
        expense = int(row.get("expense") or 0)
        if expense <= 0:
            continue
        label = _expense_category_label(row.get("sector") or "", row.get("category") or "")
        item = grouped.setdefault(label, {
            "category": label,
            "expense": 0,
            "transaction_count": 0,
        })
        item["expense"] += expense
        item["transaction_count"] += int(row.get("transaction_count") or 0)
    return sorted(grouped.values(), key=lambda row: row["expense"], reverse=True)


def _top_income_rows(result):
    rows = (result or {}).get("income") or []
    output = []
    for row in rows[:10]:
        output.append({
            "name": row.get("customer_name") or row.get("item") or row.get("category") or "-",
            "sector": row.get("sector") or "-",
            "category": row.get("category") or "-",
            "amount": int(row.get("amount") or row.get("total_amount") or 0),
            "received": int(row.get("amount_received") or 0),
            "outstanding": int(row.get("outstanding_amount") or 0),
        })
    return output


def _management_ai_payload(report):
    scopes = {}
    for scope in ("Overall", "Farm", "Sote Phwar"):
        data = _scope_financials(report, scope)
        scopes[scope] = {
            "revenue": data.get("revenue", 0),
            "expense": data.get("expense", 0),
            "profit": data.get("profit", 0),
            "margin": data.get("margin", 0),
            "top_income": (data.get("top_income") or [])[:5],
            "top_expense_categories": (data.get("expense_categories") or [])[:5],
            "source_note": data.get("source_note") or "",
        }
    return {
        "period": report.get("reporting_period"),
        "changes": report.get("changes") or {},
        "scopes": scopes,
        "receivables": report.get("receivables", 0),
        "collected": report.get("collected", 0),
        "inventory_qty": (report.get("kpi") or {}).get("inventory_qty", 0),
        "production_volume": report.get("production_volume", 0),
    }


def _extract_json_object(text):
    if not text:
        return None
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except (TypeError, ValueError):
        return None


def _normalize_ai_commentary(raw):
    if not isinstance(raw, dict):
        return {}
    output = {}
    aliases = {
        "overall": ("overall", "overall_analysis", "overall analysis"),
        "farm": ("farm", "farm_analysis", "farm_sector", "farm sector", "farm sector analysis"),
        "sotephwar": (
            "sotephwar",
            "sote_phwar",
            "sote phwar",
            "sotephwar_analysis",
            "sote_phwar_analysis",
            "sote phwar analysis",
            "sotephwar_sector",
            "sote phwar sector",
            "sote phwar sector analysis",
        ),
        "risks": ("risks", "risk", "risk_analysis", "risk analysis"),
        "recommendations": ("recommendations", "recommendation", "actions", "recommended_actions"),
        "management_conclusion": (
            "management_conclusion",
            "management conclusion",
            "conclusion",
            "management_summary",
        ),
    }
    lowered_raw = {str(key).lower().strip(): value for key, value in raw.items()}
    for key, names in aliases.items():
        value = None
        for name in names:
            if name in lowered_raw:
                value = lowered_raw[name]
                break
        if isinstance(value, list):
            output[key] = [str(item).strip() for item in value if str(item).strip()][:4]
        elif isinstance(value, str) and value.strip():
            output[key] = [line.strip(" -") for line in value.splitlines() if line.strip()][:4]
    return output


def _fallback_ai_commentary_from_text(text):
    lines = [line.strip(" -") for line in str(text or "").splitlines() if line.strip()]
    if not lines:
        return {}
    return {"overall": lines[:4]}


def _ai_commentary_lines(commentary, key):
    return (commentary or {}).get(key) or []


def _ceo_ai_commentary(question, report):
    payload = _management_ai_payload(report)
    prompt = f"""
You are BigShot CFO advisor using Qwen 3 14B.

Use only the calculated data below. Do not invent numbers. Do not recalculate totals.
Write short business analysis and management recommendations for a KPI management PDF.
Return only valid JSON with these keys:
overall, farm, sotephwar, risks, recommendations, management_conclusion.
Each value must be an array of 2 to 4 short bullet strings.

Question:
{question}

Calculated data:
{json.dumps(payload, indent=2, ensure_ascii=False, default=str)}
"""
    try:
        response = ask_ai(prompt, timeout=120).strip()
    except Exception as exc:
        return {
            "overall": [
                f"AI commentary unavailable: {exc.__class__.__name__}. "
                "Report uses calculated data and rule-based commentary."
            ],
            "risks": [
                "AI risk commentary unavailable; use the calculated KPI, expense, cash, and receivable tables for review."
            ],
            "recommendations": [
                "Retry after confirming local Qwen/Ollama is running, then regenerate the KPI PDF."
            ],
            "management_conclusion": [
                "AI management conclusion was not generated for this run."
            ],
        }
    parsed = _extract_json_object(response)
    if parsed is None:
        return _fallback_ai_commentary_from_text(response)
    normalized = _normalize_ai_commentary(parsed)
    if not normalized:
        return _fallback_ai_commentary_from_text(response)
    return normalized


def _sector_expense_label(sector, category):
    if sector == "SP Extension":
        return f"Extension / {category or '-'}"
    if sector == "SP Production":
        return f"Production / {category or '-'}"
    return category or "-"


def _ceo_sector_analysis(sectors, categories):
    analysis = {
        "Sote Phwar": {
            "revenue": 0,
            "expense": 0,
            "profit": 0,
            "margin": 0,
            "expense_categories": [],
            "top_income": [],
            "source_note": (
                "Includes Sotephwar_Transection income and Transection sectors "
                "Sote Phwar, SP Extension, and SP Production. Extension is treated "
                "inside Sote Phwar expense control."
            ),
        },
        "Farm": {
            "revenue": 0,
            "expense": 0,
            "profit": 0,
            "margin": 0,
            "expense_categories": [],
            "top_income": [],
            "source_note": (
                "Includes Farm_Transection income and Transection sector Farm."
            ),
        },
    }

    for row in sectors:
        key = _business_unit_for_sector(row.get("sector") or "")
        if not key:
            continue
        analysis[key]["revenue"] += int(row.get("income") or 0)
        analysis[key]["expense"] += int(row.get("expense") or 0)
        analysis[key]["profit"] += int(row.get("profit") or 0)

    grouped_categories = {
        "Sote Phwar": {},
        "Farm": {},
    }
    for row in categories:
        sector = row.get("sector") or ""
        key = _business_unit_for_sector(sector)
        if not key:
            continue
        expense = int(row.get("expense") or 0)
        if expense <= 0:
            continue
        label = _sector_expense_label(sector, row.get("category") or "")
        item = grouped_categories[key].setdefault(label, {
            "category": label,
            "expense": 0,
            "transaction_count": 0,
        })
        item["expense"] += expense
        item["transaction_count"] += int(row.get("transaction_count") or 0)

    for key, data in analysis.items():
        revenue = data["revenue"]
        data["margin"] = round((data["profit"] / revenue) * 100, 2) if revenue else 0
        data["expense_categories"] = sorted(
            grouped_categories[key].values(),
            key=lambda row: row["expense"],
            reverse=True,
        )[:8]

    return analysis


def _ceo_report_data(question):
    months = _period_months(12)
    monthly = []
    for year, month in months:
        period = _month_period(year, month)
        kpi = _safe_call(kpi_overview, period, default={})
        sector = _safe_call(sector_summary, period, default={})
        monthly.append({
            "period": period,
            "label": _month_label(year, month),
            "revenue": int(kpi.get("total_income") or 0),
            "gross_profit": int(kpi.get("net_profit") or kpi.get("gross_profit") or 0),
            "net_profit": int(kpi.get("net_profit") or 0),
            "margin": float(kpi.get("profit_margin_percent") or 0),
            "sectors": sector.get("sectors") or [],
        })

    trend_current = monthly[-1] if monthly else {}
    trend_previous = monthly[-2] if len(monthly) > 1 else {}
    current_period = _ceo_report_period(question, trend_current.get("period") or "this_month")
    kpi = _safe_call(kpi_overview, current_period, default={})
    previous_period = _ceo_previous_period(current_period)
    previous_kpi = _safe_call(kpi_overview, previous_period, default={}) if previous_period else {}
    sectors = (_safe_call(sector_summary, current_period, default={}) or {}).get("sectors") or []
    categories = (_safe_call(category_summary, current_period, default={}) or {}).get("categories") or []
    expense_categories = _ceo_expense_categories(categories)
    cash = _safe_call(cash_flow, current_period, default={})
    sotephwar_sales = _safe_call(sotephwar_transection_summary, current_period, default={})
    overall_top_income = _top_income_rows(_safe_call(top_income, current_period, None, 10, default={}))
    farm_top_income = _top_income_rows(_safe_call(top_income, current_period, {"sector": "Farm"}, 10, default={}))
    sotephwar_top_income = _top_income_rows(_safe_call(top_income, current_period, {"sector": "Sote Phwar"}, 10, default={}))
    inventory_value = _safe_call(calculate_inventory_value, default={}) or {}
    stock = inventory_value.get("stock") or (_safe_call(sotephwar_inventory_stock, default={}) or {}).get("stock") or []
    movements = (_safe_call(sotephwar_inventory_movement_summary, current_period, default={}) or {}).get("movements") or []
    customers = sorted(
        (sotephwar_sales.get("customers") or []),
        key=lambda row: int(row.get("outstanding_amount") or 0),
        reverse=True,
    )
    total_stock_qty = sum(int(row.get("stock_qty") or 0) for row in stock)
    production_volume = sum(
        int(row.get("quantity") or 0)
        for row in movements
        if "production" in str(row.get("type") or "").lower()
    )
    if not production_volume:
        production_volume = sum(int(row.get("quantity") or 0) for row in movements)

    business_units = _ceo_business_units(sectors)
    sector_analysis = _ceo_sector_analysis(sectors, categories)
    sector_analysis["Farm"]["top_income"] = farm_top_income
    sector_analysis["Sote Phwar"]["top_income"] = sotephwar_top_income

    previous_revenue = previous_kpi.get("total_income", trend_previous.get("revenue", 0))
    previous_profit = previous_kpi.get("net_profit", trend_previous.get("net_profit", 0))
    revenue_change = _change_percent(kpi.get("total_income", 0), previous_revenue)
    profit_change = _change_percent(kpi.get("net_profit", 0), previous_profit)
    expense_total = int(kpi.get("total_expense") or 0)
    report = {
        "question": question,
        "reporting_period": _ceo_period_label(current_period, trend_current.get("label") or datetime.now().strftime("%B %Y")),
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "monthly": monthly,
        "period": current_period,
        "kpi": {
            "revenue": int(kpi.get("total_income") or trend_current.get("revenue") or 0),
            "gross_profit": int(kpi.get("net_profit") or trend_current.get("gross_profit") or 0),
            "net_profit": int(kpi.get("net_profit") or trend_current.get("net_profit") or 0),
            "cash": int(cash.get("net_cash_flow") or 0),
            "inventory_value": int(inventory_value.get("total_inventory_value") or 0),
            "inventory_qty": total_stock_qty,
            "margin": float(kpi.get("profit_margin_percent") or trend_current.get("margin") or 0),
            "expense": expense_total,
        },
        "changes": {"revenue": revenue_change, "net_profit": profit_change},
        "business_units": business_units,
        "sector_analysis": sector_analysis,
        "top_income": overall_top_income,
        "expense_categories": expense_categories[:10],
        "customers": customers[:10],
        "receivables": int(sotephwar_sales.get("outstanding_amount") or 0),
        "collected": int(sotephwar_sales.get("amount_received") or 0),
        "stock": stock,
        "movements": movements,
        "production_volume": production_volume,
    }
    report["ai_commentary"] = _ceo_ai_commentary(question, report)
    return report


def _ceo_page(pdf, page_no, title, report):
    if page_no > 1:
        pdf.new_page()
    pdf.rect(0, 0, 595, 842, fill=(255, 255, 255))
    pdf.rect(42, 790, 34, 24, fill=(17, 24, 39))
    pdf.text(49, 798, "BS", size=10, bold=True, color=(255, 255, 255))
    pdf.text(84, 805, "BigShot Company Limited", size=10.5, bold=True, color=(31, 41, 55))
    pdf.text(84, 790, "CEO Business Report", size=8.2, color=(107, 114, 128))
    pdf.text(425, 805, f"Generated: {report['generated']}", size=7.8, color=(107, 114, 128))
    pdf.line(42, 778, 553, 778, color=(209, 213, 219))
    pdf.text(42, 750, title, size=17, bold=True)
    pdf.text(520, 28, f"Page {page_no}", size=8, color=(107, 114, 128))


def _trend_color(value):
    if value is None or value == 0:
        return (75, 85, 99)
    return (22, 163, 74) if value > 0 else (220, 38, 38)


def _draw_ceo_kpi_card(pdf, x, y, label, value, change=None, width=96, height=74):
    pdf.rect(x, y - height, width, height, fill=(249, 250, 251), stroke=(209, 213, 219))
    pdf.text(x + 8, y - 17, label, size=7.8, bold=True, color=(75, 85, 99))
    pdf.text(x + 8, y - 38, value, size=9.1, bold=True, max_width=width - 12)
    if change is not None:
        sign = "+" if change > 0 else ""
        pdf.text(x + 8, y - 62, f"Change: {sign}{change}%", size=7.1, bold=True, color=_trend_color(change))


def _draw_ceo_table(pdf, headers, rows, x=42, y=610, widths=None, font_size=7.8):
    table = [headers] + rows
    _draw_table(pdf, table, start_y=y, column_widths=widths, font_size=font_size, line_gap=11, min_row_height=24)


def _draw_ceo_kpi_dashboard(pdf, report, x=42, y=455):
    kpi = report["kpi"]
    rows = [
        ("Revenue", _mmk(kpi["revenue"]), "-", _change_label(report["changes"].get("revenue")), _trend_label(report["changes"].get("revenue"))),
        ("Expenses", _mmk(kpi["expense"]), "-", "-", "Monitor"),
        ("Net Profit", _mmk(kpi["net_profit"]), "-", _change_label(report["changes"].get("net_profit")), _trend_label(report["changes"].get("net_profit"))),
        ("Profit Margin %", f"{kpi['margin']}%", "-", "-", "Monitor"),
        ("Outstanding Receivables", _mmk(report.get("receivables", 0)), "-", "-", "Collection risk" if report.get("receivables") else "Stable"),
        ("Inventory Value", _mmk(kpi["inventory_value"]), "-", "-", "Valued"),
        ("Cash Position", _mmk(kpi["cash"]), "-", "-", "Cash pressure" if kpi["cash"] < 0 else "Stable"),
        ("Loan Balance", "-", "-", "-", "Not available"),
    ]
    pdf.text(x, y, "KPI Dashboard", size=11, bold=True)
    _draw_ceo_table(pdf, ("KPI", "Current", "Previous", "Change %", "Trend"), rows, y=y - 25, widths=[145, 105, 80, 80, 105], font_size=7.3)


def _draw_ceo_line_chart(pdf, title, rows, key, x=55, y=500, width=475, height=150):
    pdf.text(x, y + height + 28, title, size=10.2, bold=True)
    values = [(row["label"], int(row.get(key) or 0)) for row in rows]
    _draw_line_chart(pdf, values, x=x, y=y, width=width, height=height)


def _draw_ceo_bar_chart(pdf, title, rows, x=55, y=455, width=475, height=160):
    pdf.text(x, y + height + 28, title, size=10.2, bold=True)
    spec = {"values": rows}
    _draw_bar(pdf, spec, x=x, y=y, width=width, height=height)


def _draw_ceo_pie(pdf, title, rows, x=50, y=465):
    pdf.text(x, y + 170, title, size=10.2, bold=True)
    _draw_pie({"text": None} if False else pdf, {"values": rows}, cx=x + 145, cy=y + 70, radius=62)


def _draw_ceo_paragraph(pdf, title, lines, x=42, y=220):
    pdf.text(x, y, title, size=10.5, bold=True)
    yy = y - 20
    for line in lines:
        yy -= pdf.text(x, yy, line, size=8.8, max_width=510)
    return yy


def _scope_financials(report, scope):
    if scope == "Overall":
        kpi = report["kpi"]
        return {
            "revenue": int(kpi.get("revenue") or 0),
            "expense": int(kpi.get("expense") or 0),
            "profit": int(kpi.get("net_profit") or 0),
            "margin": kpi.get("margin", 0),
            "expense_categories": report.get("expense_categories") or [],
            "top_income": report.get("top_income") or [],
            "source_note": (
                "Overall combines Sote Phwar and Farm. Sote Phwar uses Sotephwar_Transection "
                "and Transection Sote Phwar/SP Extension/SP Production; Farm uses "
                "Farm_Transection and Transection Farm."
            ),
        }
    return (report.get("sector_analysis") or {}).get(scope) or {}


def _scope_monthly_rows(report, scope):
    if scope == "Overall":
        return report.get("monthly") or []
    rows = []
    for month in report.get("monthly") or []:
        revenue = 0
        expense = 0
        profit = 0
        for sector in month.get("sectors") or []:
            if _business_unit_for_sector(sector.get("sector") or "") != scope:
                continue
            revenue += int(sector.get("income") or 0)
            expense += int(sector.get("expense") or 0)
            profit += int(sector.get("profit") or 0)
        rows.append({
            "label": month.get("label"),
            "revenue": revenue,
            "expense": expense,
            "net_profit": profit,
            "margin": round((profit / revenue) * 100, 2) if revenue else 0,
        })
    return rows


def _scope_customer_rows(report, scope):
    if scope == "Sote Phwar":
        rows = []
        for row in report.get("customers") or []:
            rows.append({
                "name": row.get("customer_name") or row.get("item") or "-",
                "amount": int(row.get("total_amount") or row.get("amount") or 0),
                "received": int(row.get("amount_received") or 0),
                "outstanding": int(row.get("outstanding_amount") or 0),
            })
        return rows
    return _scope_financials(report, scope).get("top_income") or []


def _scope_ai_key(scope):
    return {
        "Overall": "overall",
        "Farm": "farm",
        "Sote Phwar": "sotephwar",
    }.get(scope, "overall")


def _scope_ai_lines(report, scope):
    commentary = report.get("ai_commentary") or {}
    key = _scope_ai_key(scope)
    lines = _ai_commentary_lines(commentary, key)
    if lines:
        return lines
    if scope != "Overall" and _ai_commentary_lines(commentary, "overall"):
        return [f"Qwen did not return dedicated {scope} commentary for this run."]
    return ["AI commentary was not generated for this run."]


def _draw_scope_kpi_page(pdf, page_no, report, scope):
    data = _scope_financials(report, scope)
    title = "BigShot Company Limited\nKPI Management Report" if scope == "Overall" else f"{scope} KPI Dashboard"
    _ceo_page(pdf, page_no, title, report)
    pdf.text(42, 710, f"Reporting period: {report['reporting_period']}", size=9.2, bold=True, color=(75, 85, 99))
    if scope == "Overall":
        pdf.text(42, 688, "Overall KPI Dashboard", size=10.5, bold=True)
    cards = [
        ("Revenue", _mmk(data.get("revenue", 0)), report["changes"].get("revenue") if scope == "Overall" else None),
        ("Expense", _mmk(data.get("expense", 0)), None),
        ("Profit", _mmk(data.get("profit", 0)), report["changes"].get("net_profit") if scope == "Overall" else None),
        ("Margin", f"{data.get('margin', 0)}%", None),
    ]
    for index, card in enumerate(cards):
        _draw_ceo_kpi_card(pdf, 42 + index * 122, 660, *card, width=112)
    heading = "Executive Summary" if scope == "Overall" else "Scope Definition"
    _draw_ceo_paragraph(pdf, heading, [
        data.get("source_note") or "",
        f"{scope} revenue is {_mmk(data.get('revenue', 0))}; expense is {_mmk(data.get('expense', 0))}; profit is {_mmk(data.get('profit', 0))}.",
    ], y=540)
    _draw_ceo_table(pdf, ("Metric", "Amount"), [
        ("Revenue", _mmk(data.get("revenue", 0))),
        ("Expense", _mmk(data.get("expense", 0))),
        ("Profit", _mmk(data.get("profit", 0))),
        ("Profit Margin", f"{data.get('margin', 0)}%"),
    ], y=430, widths=[220, 220])
    _draw_ceo_paragraph(pdf, "AI Commentary", _scope_ai_lines(report, scope), y=250)


def _draw_scope_revenue_page(pdf, page_no, report, scope):
    data = _scope_financials(report, scope)
    monthly = _scope_monthly_rows(report, scope)
    title = "Revenue Analysis" if scope == "Overall" else f"{scope} Revenue Analysis"
    _ceo_page(pdf, page_no, title, report)
    _draw_ceo_line_chart(pdf, "Revenue Trend Line Chart - Last 12 Months", monthly, "revenue", y=505)
    top_rows = data.get("top_income") or []
    table_rows = [
        (row.get("name") or "-", row.get("sector") or scope, _mmk(row.get("amount", 0)), _mmk(row.get("outstanding", 0)))
        for row in top_rows[:8]
    ]
    pdf.text(42, 375, "Top Income", size=10.5, bold=True)
    _draw_ceo_table(pdf, ("Customer / Item", "Sector", "Income", "Outstanding"), table_rows, y=345, widths=[210, 95, 105, 105], font_size=7.2)
    top_name = top_rows[0]["name"] if top_rows else "no income row"
    _draw_ceo_paragraph(pdf, "Analyst Commentary", [
        f"{scope} top income source is {top_name}. This table is included so revenue concentration is visible before margin decisions.",
        "Revenue should be reviewed together with outstanding amounts because billed income and collected cash can move differently.",
    ], y=115)


def _draw_scope_profitability_page(pdf, page_no, report, scope):
    data = _scope_financials(report, scope)
    monthly = _scope_monthly_rows(report, scope)
    title = "Profitability Analysis" if scope == "Overall" else f"{scope} Profitability Analysis"
    _ceo_page(pdf, page_no, title, report)
    _draw_ceo_line_chart(pdf, "Profit Trend Line Chart", monthly, "net_profit", y=520)
    _draw_ceo_line_chart(pdf, "Profit Margin Trend Line Chart", monthly, "margin", y=300, height=125)
    _draw_ceo_paragraph(pdf, "Analyst Commentary", [
        f"{scope} profit is {_mmk(data.get('profit', 0))} with {data.get('margin', 0)}% margin.",
        "Margin pressure appears when expenses grow faster than revenue or when revenue is high but collection is weak.",
    ], y=120)


def _draw_scope_expense_page(pdf, page_no, report, scope, detail=False):
    data = _scope_financials(report, scope)
    expense_rows = data.get("expense_categories") or []
    title_prefix = "Expense Detail Analysis" if detail else "Expense Analysis"
    title = title_prefix if scope == "Overall" else f"{scope} {title_prefix}"
    _ceo_page(pdf, page_no, title, report)
    if detail:
        table_rows = [
            (row.get("category") or "-", _mmk(row.get("expense", 0)), row.get("transaction_count", 0))
            for row in expense_rows[:12]
        ]
        _draw_ceo_table(pdf, ("Category", "Expense", "Rows"), table_rows, y=705, widths=[285, 145, 80], font_size=7.4)
        _draw_ceo_paragraph(pdf, "Control Focus", [
            "This page expands the expense category list for budget review and approval control.",
            "Use repeated high-value categories as candidates for owner-level limits.",
        ], y=220)
        return
    pie_rows = [(row.get("category") or "-", row.get("expense", 0)) for row in expense_rows[:6]]
    _draw_ceo_pie(pdf, "Expense Breakdown by Category", pie_rows, x=42, y=480)
    table_rows = [
        (row.get("category") or "-", _mmk(row.get("expense", 0)), row.get("transaction_count", 0))
        for row in expense_rows[:8]
    ]
    _draw_ceo_table(pdf, ("Category", "Expense", "Rows"), table_rows, y=410, widths=[260, 140, 95])
    top_category = expense_rows[0]["category"] if expense_rows else "no expense category"
    _draw_ceo_paragraph(pdf, "Analyst Commentary", [
        f"The largest visible {scope} expense category is {top_category}.",
        "Expense movement should be compared with revenue before reducing or increasing operating budgets.",
    ], y=170)


def _draw_scope_customer_page(pdf, page_no, report, scope):
    title = "Customer Analysis" if scope == "Overall" else f"{scope} Customer Analysis"
    _ceo_page(pdf, page_no, title, report)
    rows = _scope_customer_rows(report, scope)
    table_rows = [
        (
            row.get("name") or "-",
            _mmk(row.get("amount", 0)),
            _mmk(row.get("received", 0)),
            _mmk(row.get("outstanding", 0)),
        )
        for row in rows[:12]
    ]
    _draw_ceo_table(pdf, ("Customer / Item", "Revenue", "Received", "Outstanding"), table_rows, y=705, widths=[210, 105, 95, 105], font_size=7.2)
    _draw_ceo_paragraph(pdf, "Collection Commentary", [
        "High-value customers or items should be checked for repeatability and collection timing.",
        "Outstanding balances should be reviewed before treating revenue growth as usable cash.",
    ], y=170)


def _draw_ai_commentary_page(pdf, page_no, report):
    _ceo_page(pdf, page_no, "AI Commentary", report)
    commentary = report.get("ai_commentary") or {}
    sections = [
        ("Overall Analysis", _scope_ai_lines(report, "Overall")),
        ("Farm Sector Analysis", _scope_ai_lines(report, "Farm")),
        ("Sote Phwar Sector Analysis", _scope_ai_lines(report, "Sote Phwar")),
        ("Risks", _ai_commentary_lines(commentary, "risks") or _risk_lines_for_report(report)),
        ("Recommendations", _ai_commentary_lines(commentary, "recommendations") or [
            "Review the largest expense category first and confirm the next action owner.",
            "Use top income and outstanding balance tables together before making growth decisions.",
        ]),
        ("Management Conclusion", _ai_commentary_lines(commentary, "management_conclusion") or [
            "AI management conclusion was not generated for this run.",
        ]),
    ]
    y = 710
    for title, lines in sections:
        y = _draw_ceo_paragraph(pdf, title, lines, y=y)
        y -= 12
        if y < 90:
            pdf.new_page()
            y = 760


def _draw_sector_analysis_page(pdf, page_no, title, report, sector_name):
    sector = (report.get("sector_analysis") or {}).get(sector_name) or {}
    revenue = int(sector.get("revenue") or 0)
    expense = int(sector.get("expense") or 0)
    profit = int(sector.get("profit") or 0)
    margin = sector.get("margin", 0)
    expense_rows = sector.get("expense_categories") or []

    _ceo_page(pdf, page_no, title, report)
    pdf.text(42, 710, f"Reporting period: {report['reporting_period']}", size=9.2, bold=True, color=(75, 85, 99))
    cards = [
        ("Revenue", _mmk(revenue), None),
        ("Expense", _mmk(expense), None),
        ("Profit", _mmk(profit), None),
        ("Margin", f"{margin}%", None),
    ]
    for index, card in enumerate(cards):
        _draw_ceo_kpi_card(pdf, 42 + index * 122, 665, *card, width=112)

    pdf.text(42, 560, "Sector KPI Summary", size=10.5, bold=True)
    summary_rows = [
        ("Revenue", _mmk(revenue)),
        ("Expense", _mmk(expense)),
        ("Profit", _mmk(profit)),
        ("Profit Margin", f"{margin}%"),
    ]
    _draw_ceo_table(pdf, ("Metric", "Amount"), summary_rows, y=530, widths=[220, 220])

    chart_rows = [(row.get("category") or "-", row.get("expense", 0)) for row in expense_rows[:6]]
    if chart_rows:
        _draw_ceo_bar_chart(pdf, "Top Expense Categories", chart_rows, y=255, height=115)
    table_rows = [
        (row.get("category") or "-", _mmk(row.get("expense", 0)), row.get("transaction_count", 0))
        for row in expense_rows[:6]
    ]
    _draw_ceo_table(pdf, ("Category", "Expense", "Rows"), table_rows, y=210, widths=[260, 140, 95], font_size=7.4)

    top_category = expense_rows[0]["category"] if expense_rows else "no expense category"
    _draw_ceo_paragraph(pdf, "Analyst Commentary", [
        sector.get("source_note") or "",
        f"{sector_name} profit is {_mmk(profit)} on revenue of {_mmk(revenue)}. The largest visible cost driver is {top_category}.",
        "Management should compare this sector page with the overall KPI page before changing budgets, because shared cash pressure can come from either sector.",
    ], y=110)


def _change_label(value):
    if value is None:
        return "-"
    sign = "+" if value > 0 else ""
    return f"{sign}{value}%"


def _trend_label(value):
    if value is None:
        return "No baseline"
    if value > 5:
        return "Growing"
    if value < -5:
        return "Contracting"
    return "Stable"


def _risk_lines_for_report(report):
    kpi = report["kpi"]
    risks = []
    revenue_change = report["changes"].get("revenue")
    profit_change = report["changes"].get("net_profit")
    if revenue_change is not None and revenue_change < -10:
        risks.append(f"Revenue declined {_change_label(revenue_change)}, above the 10% management threshold.")
    if profit_change is not None and profit_change < -10:
        risks.append(f"Profit declined {_change_label(profit_change)}, requiring margin and cost review.")
    if report.get("receivables", 0) > 0:
        risks.append(f"Outstanding receivables are {_mmk(report['receivables'])}; collection follow-up should be prioritized by customer.")
    if not report.get("stock"):
        risks.append("Potential Data Quality Issue Detected: inventory stock data is not available for valuation.")
    if kpi.get("cash", 0) < 0:
        risks.append(f"Cash position is negative at {_mmk(kpi['cash'])}, indicating possible short-term cash pressure.")
    return risks or ["No critical risk threshold was triggered by the available data."]


def create_ceo_management_pdf_report(question, output_path, title="BigShot CEO Management Report"):
    report = _ceo_report_data(question)
    kpi = report["kpi"]
    units = report["business_units"]
    use_reportlab = contains_myanmar_value(report) or contains_myanmar_value(question) or contains_myanmar_value(title)
    pdf = PdfCanvas(title, use_reportlab=use_reportlab)

    page = 1
    for scope in ("Overall", "Farm", "Sote Phwar"):
        _draw_scope_kpi_page(pdf, page, report, scope)
        page += 1
        _draw_scope_revenue_page(pdf, page, report, scope)
        page += 1
        _draw_scope_profitability_page(pdf, page, report, scope)
        page += 1
        _draw_scope_expense_page(pdf, page, report, scope)
        page += 1
        _draw_scope_expense_page(pdf, page, report, scope, detail=True)
        page += 1
        _draw_scope_customer_page(pdf, page, report, scope)
        page += 1
        if scope == "Sote Phwar":
            _ceo_page(pdf, page, "Sote Phwar Inventory & Operations", report)
            stock_rows = [
                (
                    row.get("store") or "-",
                    row.get("product") or "-",
                    row.get("stock_qty", row.get("qty", 0)),
                    _mmk(row.get("inventory_value", 0)),
                )
                for row in report["stock"][:12]
            ]
            pdf.text(42, 705, f"Inventory valuation: {_mmk(kpi['inventory_value'])}", size=9.2, bold=True)
            pdf.text(42, 685, f"Total stock quantity: {kpi['inventory_qty']:,}", size=9.2, bold=True)
            pdf.text(42, 665, f"Production volume: {report['production_volume']:,}", size=9.2, bold=True)
            _draw_ceo_table(pdf, ("Store", "Product", "Qty", "Value"), stock_rows, y=625, widths=[150, 190, 65, 95])
            _draw_ceo_paragraph(pdf, "Operational Observations", [
                "Inventory valuation uses the shared Formula Engine unit-cost map and current stock movement balance.",
                "Slow-moving inventory should still be identified by aging movement rows; current data supports stock position, valuation, and production volume.",
            ], y=150)
            page += 1

    _draw_ai_commentary_page(pdf, page, report)
    page += 1

    _ceo_page(pdf, page, "Business Growth, Risks & Opportunities", report)
    growth_rows = [
        ("Revenue Growth", _change_label(report["changes"].get("revenue")), _trend_label(report["changes"].get("revenue"))),
        ("Profit Growth", _change_label(report["changes"].get("net_profit")), _trend_label(report["changes"].get("net_profit"))),
        ("Customer Growth", "-", "Data needed"),
        ("Inventory Growth", "-", "Data needed"),
    ]
    _draw_ceo_table(pdf, ("Growth KPI", "Change %", "Classification"), growth_rows, y=705, widths=[205, 145, 165])
    risk_lines = _ai_commentary_lines(report.get("ai_commentary"), "risks") or _risk_lines_for_report(report)
    y = _draw_ceo_paragraph(pdf, "Risk Analysis", risk_lines, y=500)
    total_profit = sum(abs(value["profit"]) for value in units.values()) or 1
    sote_profit_share = round((units["Sote Phwar"]["profit"] / total_profit) * 100, 1) if total_profit else 0
    _draw_ceo_paragraph(pdf, "Opportunities", [
        f"Sote Phwar contributes {sote_profit_share}% of absolute business-unit profit, so positive demand signals should be converted into disciplined growth targets.",
        "Farm can reduce concentration risk if revenue contribution improves.",
        "Inventory optimization requires unit cost and movement aging so management can separate fast-moving products from slow-moving stock.",
    ], y=y - 15)
    page += 1

    _ceo_page(pdf, page, "Recommendations & Management Conclusion", report)
    ai_recommendations = _ai_commentary_lines(report.get("ai_commentary"), "recommendations")
    ai_conclusion = _ai_commentary_lines(report.get("ai_commentary"), "management_conclusion")
    sections = [
        ("Immediate Actions (30 Days)", [
            ai_recommendations[0] if len(ai_recommendations) > 0 else f"Review the top expense category and confirm necessity before the next payment cycle; current total expense is {_mmk(kpi['expense'])}.",
            ai_recommendations[1] if len(ai_recommendations) > 1 else "Add unit cost fields to inventory records so future CEO reports can show inventory value, turnover, and margin by product.",
        ]),
        ("Medium-Term Actions (90 Days)", [
            ai_recommendations[2] if len(ai_recommendations) > 2 else "Set monthly budget thresholds for labor, logistics, marketing, and production cost categories using the expense breakdown page.",
            ai_recommendations[3] if len(ai_recommendations) > 3 else "Track revenue and profit targets separately for Sote Phwar and Farm, with Extension treated inside Sote Phwar expense control.",
        ]),
        ("Strategic Actions (12 Months)", [
            "Reduce profit concentration by scaling the business unit with the lowest revenue contribution and positive operating signals.",
            "Build a monthly management review pack around the same KPI definitions so trend lines remain comparable month to month.",
        ]),
    ]
    y = 705
    for heading, items in sections:
        pdf.text(42, y, heading, size=11, bold=True)
        y -= 20
        for item in items:
            y -= pdf.text(58, y, f"- {item}", size=8.9, max_width=485)
        y -= 16
    conclusion_lines = ai_conclusion or [
        f"Business strength versus previous period: {_trend_label(report['changes'].get('revenue'))} on revenue and {_trend_label(report['changes'].get('net_profit'))} on profit.",
        "Top 3 management priorities: cash collection, profit margin protection, and inventory costing discipline.",
        "CEO focus next: convert the highest-confidence revenue driver into a target while controlling the largest expense category.",
        "What should management do next? Use this report as the monthly decision pack and assign owners to cash, margin, revenue, inventory, and debt actions.",
    ]
    _draw_ceo_paragraph(pdf, "Management Conclusion", conclusion_lines, y=max(245, y))

    pdf.finish(output_path)
    return True


def create_chart_pdf_report(question, output_path, title="BigShot Finance Report"):
    if _is_ceo_management_report_question(question):
        return create_ceo_management_pdf_report(question, output_path, title="BigShot CEO Management Report")

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

    use_reportlab = (
        contains_myanmar_value(result)
        or contains_myanmar_value(spec)
        or contains_myanmar_value(question)
        or contains_myanmar_value(title)
    )

    if not use_reportlab and _should_use_unicode_text_pdf(result, spec, question, title):
        unicode_lines = _unicode_pdf_lines(title, question, spec)
        if unicode_lines and _write_unicode_text_pdf(unicode_lines, output_path, title=title):
            return True

    pdf = PdfCanvas(title, use_reportlab=use_reportlab)
    _draw_header(pdf, title, question)

    kind = spec.get("kind")
    if kind == "voucher_cards":
        pdf.text(50, 720, spec["title"], size=12, bold=True)
        vouchers = spec.get("vouchers") or []
        _draw_voucher_summary(pdf, vouchers, y=698)
        _draw_voucher_cards(pdf, vouchers, start_y=638)
        pdf.finish(output_path)
        return True

    if kind == "voucher_table":
        pdf.text(50, 720, spec["title"], size=12, bold=True)
        vouchers = spec.get("vouchers") or []
        _draw_voucher_summary(pdf, vouchers, y=698)
        _draw_voucher_table(pdf, vouchers, start_y=620)
        pdf.finish(output_path)
        return True

    if kind == "pie" and result.get("formula") == "sales_total":
        pdf.text(50, 720, spec["title"], size=12, bold=True)
        _draw_pie(pdf, spec)
        pdf.text(50, 415, "Data Table", size=12, bold=True)
        _draw_table(pdf, spec.get("table"), start_y=392)
        income_rows = spec.get("income_rows") or []
        if income_rows:
            pdf.new_page()
            pdf.text(50, 795, "Transection Income", size=13, bold=True)
            rows = [("Date", "Item", "Amount", "Payment")] + [
                (row.get("Date") or "-", row.get("item") or "-", row.get("amount") or 0, row.get("payment_method") or "-")
                for row in income_rows
            ]
            _draw_table(pdf, rows, start_y=760)
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

    if kind == "customer_revenue_report":
        _draw_customer_revenue_report(pdf, spec, start_y=720)
        pdf.finish(output_path)
        return True

    if kind == "financial_total_report":
        _draw_financial_total_report(pdf, spec)
        pdf.finish(output_path)
        return True

    if kind == "financial_category_report":
        _draw_financial_category_report(pdf, spec)
        pdf.finish(output_path)
        return True

    if kind == "income_category_report":
        _draw_income_category_report(pdf, spec)
        pdf.finish(output_path)
        return True

    if kind == "income_detail_report":
        _draw_income_detail_report(pdf, spec)
        pdf.finish(output_path)
        return True

    if kind == "income_summary_report":
        _draw_income_summary_report(pdf, spec)
        pdf.finish(output_path)
        return True

    if kind == "financial_detail_report":
        _draw_financial_detail_report(pdf, spec)
        pdf.finish(output_path)
        return True

    if kind == "transaction_ledger_report":
        _draw_transaction_ledger_report(pdf, spec)
        pdf.finish(output_path)
        return True

    if kind == "expense_comparison_report":
        _draw_expense_comparison_report(pdf, spec)
        pdf.finish(output_path)
        return True

    if kind == "master_compare_report":
        _draw_master_compare_report(pdf, spec)
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
