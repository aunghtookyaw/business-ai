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
    if result.get("formula") == "expense_period_comparison":
        return result.get("categories") or []
    for key in (
        "transactions", "expenses", "income", "categories", "sectors", "invoices",
        "customers", "stock", "movements", "months", "summary", "obligations",
    ):
        rows = result.get(key)
        if rows:
            return rows
    return []


INCOME_DETAIL_COLUMNS = (
    ("Date", 10, "left"),
    ("Item", 25, "left"),
    ("Sector", 12, "left"),
    ("Category", 25, "left"),
    ("Payment", 12, "left"),
    ("Amount", 15, "right"),
)


def _fixed_cell(value, width, align):
    text = "" if value is None else str(value)
    if len(text) > width:
        text = text[:width]
    if align == "right":
        return text.rjust(width)
    return text.ljust(width)


def _fixed_row(columns, values):
    return " ".join(
        _fixed_cell(value, width, align)
        for (_, width, align), value in zip(columns, values)
    )


def _is_income_detail_payload(payload):
    intent = payload.get("intent") or {}
    result = payload.get("result") or {}
    return (
        result.get("formula") == "list_transactions"
        and intent.get("module") == "income"
        and intent.get("report") in {"income_detail", "income_transactions"}
    )


def _fixed_income_detail_lines(result):
    rows = result.get("transactions") or []
    lines = [
        "Income Detail",
        _fixed_row(INCOME_DETAIL_COLUMNS, [column[0] for column in INCOME_DETAIL_COLUMNS]),
    ]
    separator_length = sum(column[1] for column in INCOME_DETAIL_COLUMNS) + len(INCOME_DETAIL_COLUMNS) - 1
    lines.append("-" * separator_length)
    if not rows:
        lines.append("No matching income rows found.")
        return lines

    for row in rows:
        lines.append(_fixed_row(INCOME_DETAIL_COLUMNS, [
            row.get("Date") or row.get("date") or "-",
            row.get("item") or "-",
            row.get("sector") or "-",
            row.get("category") or "-",
            row.get("payment_method") or row.get("payment") or "-",
            _money(int(row.get("amount") or 0)),
        ]))
    return lines


def _customer_revenue_lines(result, customers, total_sales_key, total_paid_key=None, total_outstanding_key=None):
    sorted_customers = sorted(
        customers or [],
        key=lambda row: int(row.get("total_amount") or row.get("amount") or row.get("income") or 0),
        reverse=True,
    )
    total_sales = int(result.get(total_sales_key) or sum(int(row.get("total_amount") or row.get("amount") or row.get("income") or 0) for row in sorted_customers) or 0)
    if total_paid_key and total_paid_key in result:
        total_paid = int(result.get(total_paid_key) or 0)
    else:
        total_paid = sum(int(row.get("amount_received", row.get("total_amount", row.get("income", 0))) or 0) for row in sorted_customers)
    if total_outstanding_key and total_outstanding_key in result:
        total_outstanding = int(result.get(total_outstanding_key) or 0)
    else:
        total_outstanding = sum(int(row.get("outstanding_amount") or 0) for row in sorted_customers)

    lines = [
        "KPI Summary",
        f"Total Sales: {_money(total_sales)}",
        f"Total Paid: {_money(total_paid)}",
        f"Total Outstanding: {_money(total_outstanding)}",
        "",
        "Top Customers by Revenue",
    ]
    if not sorted_customers:
        lines.append("No customer sales found.")
    for index, row in enumerate(sorted_customers[:10], start=1):
        sales = int(row.get("total_amount") or row.get("amount") or row.get("income") or 0)
        paid = int(row.get("amount_received", sales) or 0)
        outstanding = int(row.get("outstanding_amount") or 0)
        lines.append(
            "{index}. {customer} | Total Sales: {sales} | Paid: {paid} | Outstanding: {outstanding}".format(
                index=index,
                customer=row.get("customer_name") or row.get("item") or row.get("category") or "-",
                sales=_money(sales),
                paid=_money(paid),
                outstanding=_money(outstanding),
            )
        )
    lines.extend([
        "",
        "Customer Collection Status",
        "Customer Name | Total Sales | Paid Amount | Outstanding Amount",
    ])
    for row in sorted_customers[:20]:
        sales = int(row.get("total_amount") or row.get("amount") or row.get("income") or 0)
        paid = int(row.get("amount_received", sales) or 0)
        outstanding = int(row.get("outstanding_amount") or 0)
        lines.append(
            "{customer} | {sales} | {paid} | {outstanding}".format(
                customer=row.get("customer_name") or row.get("item") or row.get("category") or "-",
                sales=_money(sales),
                paid=_money(paid),
                outstanding=_money(outstanding),
            )
        )
    return lines


def format_text_report(payload):
    result = payload["result"]
    lines = [
        payload["title"],
        f"Period: {payload['period_label']}",
        "",
    ]

    formula = result.get("formula")
    if formula == "expense_period_comparison":
        periods = result.get("periods") or []
        categories = result.get("categories") or []
        previous = periods[0] if periods else {}
        current = periods[1] if len(periods) > 1 else {}
        lines.extend([
            "Expense Comparison",
            f"{previous.get('label', 'Previous')}: {_money(previous.get('total_expense', 0))}",
            f"{current.get('label', 'Current')}: {_money(current.get('total_expense', 0))}",
            f"Change: {_money(result.get('total_change', 0))}"
            + (f" ({result['total_change_percent']}%)" if result.get("total_change_percent") is not None else ""),
            "",
            "Local AI Comment",
            result.get("ai_comment") or "-",
            "",
            "Category Comparison Table",
            "Category | Previous | Current | Change | Change %",
        ])
        for row in categories[:20]:
            lines.append(
                "{category} | {previous} | {current} | {change} | {percent}".format(
                    category=row.get("category") or "-",
                    previous=_money(row.get("previous_amount", 0)),
                    current=_money(row.get("current_amount", 0)),
                    change=_money(row.get("change", 0)),
                    percent="-" if row.get("change_percent") is None else f"{row['change_percent']}%",
                )
            )
    elif formula == "sales_total":
        lines.append(f"Total income: {_money(result.get('total_sales', 0))}")
        if "amount_received" in result:
            lines.append(f"Paid / received: {_money(result.get('amount_received', 0))}")
        if "outstanding_amount" in result:
            lines.append(f"Remained: {_money(result.get('outstanding_amount', 0))}")
        income_rows = result.get("transection_income_rows") or []
        if income_rows:
            lines.extend(["", "Transection Income", "Date | Item | Amount | Payment"])
            for row in income_rows[:10]:
                lines.append(
                    "{date} | {item} | {amount} | {payment}".format(
                        date=row.get("Date") or "-",
                        item=row.get("item") or "-",
                        amount=_money(row.get("amount") or 0),
                        payment=row.get("payment_method") or "-",
                    )
                )
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
        lines.extend(_customer_revenue_lines(result, result.get("customers") or [], "total_amount", "amount_received", "outstanding_amount"))
    elif formula == "category_summary":
        intent = payload.get("intent") or result.get("_bi_intent") or {}
        if (
            intent.get("business") == "farm"
            and intent.get("module") == "income"
            and intent.get("report") in {"income_summary", "total_income"}
        ):
            lines.extend(_customer_revenue_lines(
                result,
                result.get("categories") or [],
                "total_income",
                "amount_received",
                "outstanding_amount",
            ))
        else:
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
    elif _is_income_detail_payload(payload):
        lines.extend(_fixed_income_detail_lines(result))
    else:
        rows = _rows_from_result(result)
        if not rows:
            lines.append("No matching data found.")
        for index, row in enumerate(rows[:20], start=1):
            lines.append(_format_row(index, row))

    if result.get("note"):
        lines.extend(["", f"Note: {result['note']}"])

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

    if payload["result"].get("formula") == "expense_period_comparison":
        _write_expense_comparison_excel(workbook, sheet, payload)
        workbook.save(output_path)
        return

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


def _write_expense_comparison_excel(workbook, sheet, payload):
    try:
        from openpyxl.chart import LineChart, Reference
    except ImportError:
        LineChart = None
        Reference = None

    result = payload["result"]
    periods = result.get("periods") or []
    categories = result.get("categories") or []
    sheet.append(["Expense Trend"])
    sheet.append(["Period", "Total Expense", "Paid", "Outstanding", "Rows"])
    for row in periods:
        sheet.append([
            row.get("label"),
            row.get("total_expense", 0),
            row.get("paid", 0),
            row.get("outstanding", 0),
            row.get("transaction_count", 0),
        ])

    if LineChart and Reference and periods:
        chart = LineChart()
        chart.title = "Expense Comparison"
        chart.y_axis.title = "Amount"
        chart.x_axis.title = "Period"
        data = Reference(sheet, min_col=2, min_row=5, max_row=4 + len(periods))
        labels = Reference(sheet, min_col=1, min_row=5, max_row=4 + len(periods))
        chart.add_data(data, titles_from_data=False)
        chart.set_categories(labels)
        sheet.add_chart(chart, "G4")

    sheet.append([])
    sheet.append(["Local AI Comment"])
    for line in (result.get("ai_comment") or "-").splitlines():
        sheet.append([line])

    sheet.append([])
    sheet.append(["Category", "Previous", "Current", "Change", "Change %"])
    for row in categories:
        sheet.append([
            row.get("category"),
            row.get("previous_amount", 0),
            row.get("current_amount", 0),
            row.get("change", 0),
            row.get("change_percent"),
        ])


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
