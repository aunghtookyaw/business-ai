import csv
import tempfile
from datetime import date
from pathlib import Path


def _money(value):
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, int):
        return f"{value:,}"
    return value


def _rows_from_result(result):
    for key in (
        "transactions", "expenses", "income", "categories", "sectors", "invoices",
        "stock", "movements", "months", "summary", "obligations",
    ):
        rows = result.get(key)
        if rows:
            return rows
    return []


def format_text_report(payload):
    result = payload["result"]
    lines = [
        payload["title"],
        f"Period: {payload['period_label']}",
        "",
    ]

    formula = result.get("formula")
    if formula == "sales_total":
        lines.append(f"Total income: {_money(result.get('total_sales', 0))}")
        if "amount_received" in result:
            lines.append(f"Paid / received: {_money(result.get('amount_received', 0))}")
        if "outstanding_amount" in result:
            lines.append(f"Remained: {_money(result.get('outstanding_amount', 0))}")
    elif formula == "expense_total":
        lines.append(f"Total expense: {_money(result.get('total_expense', 0))}")
    elif formula in {"gross_profit", "kpi_overview"}:
        lines.extend([
            f"Income: {_money(result.get('income', result.get('total_income', 0)))}",
            f"Expense: {_money(result.get('expense', result.get('total_expense', 0)))}",
            f"Profit: {_money(result.get('gross_profit', result.get('net_profit', 0)))}",
        ])
        if "profit_margin_percent" in result:
            lines.append(f"Margin: {result['profit_margin_percent']}%")
        if "amount_received" in result:
            lines.append(f"Received: {_money(result.get('amount_received', 0))}")
        if "outstanding_amount" in result:
            lines.append(f"Outstanding / unpaid: {_money(result.get('outstanding_amount', 0))}")
    elif formula == "cash_flow":
        lines.extend([
            f"Inflow: {_money(result.get('total_inflow', 0))}",
            f"Outflow: {_money(result.get('total_outflow', 0))}",
            f"Net cash flow: {_money(result.get('net_cash_flow', 0))}",
        ])
    elif formula == "sotephwar_transection_summary":
        lines.extend([
            f"Invoices: {_money(result.get('invoice_count', 0))}",
            f"Total amount: {_money(result.get('total_amount', 0))}",
            f"Received: {_money(result.get('amount_received', 0))}",
            f"Outstanding: {_money(result.get('outstanding_amount', 0))}",
        ])
    elif formula == "category_summary":
        lines.extend([
            f"Total income: {_money(result.get('total_income', 0))}",
            f"Total expense: {_money(result.get('total_expense', 0))}",
            f"Net total: {_money(result.get('net_total', 0))}",
            f"Rows: {_money(result.get('transaction_count', 0))}",
            "",
        ])
        rows = _rows_from_result(result)
        if not rows:
            lines.append("No matching data found.")
        for index, row in enumerate(rows[:20], start=1):
            lines.append(_format_row(index, row))
    else:
        rows = _rows_from_result(result)
        if not rows:
            lines.append("No matching data found.")
        for index, row in enumerate(rows[:20], start=1):
            lines.append(_format_row(index, row))

    if result.get("note"):
        lines.extend(["", f"Note: {result['note']}"])

    lines.extend(["", "Structured intent:", str(payload["intent"])])
    return "\n".join(str(line) for line in lines)


def _format_row(index, row):
    preferred = [
        "Date", "date", "invoice_date", "next_due_date", "customer_name",
        "creditor", "item", "category", "subcategory", "sector", "product",
        "store", "type", "frequency", "status", "amount", "total_amount",
        "amount_received", "outstanding_amount", "stock_qty", "quantity",
        "days_until_due", "notes",
    ]
    parts = []
    for key in preferred:
        if key in row and row[key] not in (None, ""):
            parts.append(f"{key}: {_money(row[key])}")
    if not parts:
        parts = [f"{key}: {_money(value)}" for key, value in row.items() if value not in (None, "")]
    max_parts = 10 if row.get("creditor") or row.get("next_due_date") else 8
    return f"{index}. " + " | ".join(parts[:max_parts])


def write_excel_report(payload, output_path):
    try:
        from openpyxl import Workbook
    except ImportError:
        _write_csv_fallback(payload, output_path)
        return

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Report"
    sheet.append([payload["title"]])
    sheet.append(["Period", payload["period_label"]])
    sheet.append([])

    rows = _rows_from_result(payload["result"])
    if rows:
        headers = sorted({key for row in rows for key in row.keys()})
        sheet.append(headers)
        for row in rows:
            sheet.append([row.get(header) for header in headers])
    else:
        sheet.append(["Metric", "Value"])
        for key, value in payload["result"].items():
            if key != "formula":
                sheet.append([key, value])

    workbook.save(output_path)


def _write_csv_fallback(payload, output_path):
    csv_path = Path(output_path)
    rows = _rows_from_result(payload["result"])
    with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow([payload["title"]])
        writer.writerow(["Period", payload["period_label"]])
        writer.writerow([])
        if rows:
            headers = sorted({key for row in rows for key in row.keys()})
            writer.writerow(headers)
            for row in rows:
                writer.writerow([row.get(header) for header in headers])


def write_text_pdf_report(payload, output_path, writer):
    writer(format_text_report(payload), output_path, title=payload["title"])


def temp_report_path(suffix):
    handle = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    path = Path(handle.name)
    handle.close()
    return path
