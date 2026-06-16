import json
import re
from datetime import date

from tools.formula_engine import (
    FORMULAS,
    choose_formula_by_keywords,
    is_sotephwar_transection_question,
    normalize_period,
    run_formula,
)
from tools.openclaw_client import ask_ai


FAST_FORMULAS = {
    "sales_total",
    "expense_total",
    "gross_profit",
    "kpi_overview",
    "cash_flow",
    "sector_summary",
    "category_summary",
    "top_expenses",
    "top_income",
    "list_transactions",
    "sotephwar_transection_summary",
    "sotephwar_transection_monthly_summary",
    "sotephwar_transection_top",
    "sotephwar_transection_list",
    "sotephwar_transection_quantity",
    "sotephwar_transection_customer",
    "sotephwar_payment_update",
    "sotephwar_inventory_stock",
    "sotephwar_inventory_movement_summary",
    "sotephwar_inventory_list",
    "financial_obligation_summary",
    "financial_obligation_due",
    "financial_obligation_list",
    "financial_obligation_insert",
}

ANALYSIS_KEYWORDS = (
    "analyze",
    "analysis",
    "suggest",
    "suggestion",
    "recommend",
    "recommendation",
    "advice",
    "risk",
    "problem",
    "why",
    "what should",
    "how can",
    "improve",
    "plan",
)

COMPARISON_KEYWORDS = (
    "compare",
    "comparison",
    "versus",
    " vs ",
    "month to month",
    "month over month",
    "mom",
    "year to year",
    "year over year",
    "yoy",
)

ROUTER_PROMPT = """
You route Telegram business questions to formulas.

Available formulas:
- sales_total: total sale, income, revenue
- expense_total: total expense, total cost, spending
- gross_profit: gross profit, net profit, profit
- kpi_overview: KPI, overview, margin, business status
- cash_flow: cash flow, inflow, outflow, payment method cash or m-pay
- sector_summary: sector performance, farm, SP Extension, SP Production
- category_summary: category, categorization, machinery, equipment
- top_expenses: biggest expenses, top costs
- top_income: biggest income, top sales, largest revenue
- list_transactions: transaction records for a specific date
- sotephwar_transection_summary: totals from Sotephwar_Transection only
- sotephwar_transection_monthly_summary: month-by-month income totals from Sotephwar_Transection only
- sotephwar_transection_top: top invoices from Sotephwar_Transection only
- sotephwar_transection_list: invoice rows from Sotephwar_Transection only
- sotephwar_transection_quantity: quantity sold by item from Sotephwar_Transection only
- sotephwar_transection_customer: voucher rows for one customer from Sotephwar_Transection only
- sotephwar_payment_update: update Amount_Received and Note for a Sotephwar voucher payment
- sotephwar_inventory_stock: current Sotephwar inventory stock by store and product
- sotephwar_inventory_movement_summary: Sotephwar inventory production, transfer, and sale movement totals
- sotephwar_inventory_list: Sotephwar inventory movement rows
- financial_obligation_summary: Financial_Obligations totals by category/status
- financial_obligation_due: Financial_Obligations upcoming or overdue rows
- financial_obligation_list: Financial_Obligations detail rows
- financial_obligation_insert: insert one Financial_Obligations row from an explicit add/create prompt

Financial_Obligations is for reminders only. Do not route KPI, profit,
income, expense, cash-flow, statistics, sector, category, top income, or top
expense questions to Financial_Obligations unless the user clearly asks about
obligations, due dates, reminders, creditors, loans, settlements, or fixed
payments.

Reply only valid JSON:
{"formula": "formula_name"}
"""


def _extract_json(text):
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None

    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def choose_formula(question):
    if is_sotephwar_transection_question(question):
        return choose_formula_by_keywords(question)

    if needs_comparison(question):
        return "comparison"

    if needs_analysis(question):
        return "analysis"

    keyword_formula = choose_formula_by_keywords(question)
    if keyword_formula in FAST_FORMULAS:
        return keyword_formula

    try:
        response = ask_ai(f"{ROUTER_PROMPT}\n\nQuestion: {question}")
        data = _extract_json(response)
        formula = data.get("formula") if data else None
        if formula in FORMULAS:
            return formula
    except Exception:
        pass

    return "analysis"


def needs_analysis(question):
    text = question.lower()
    return any(keyword in text for keyword in ANALYSIS_KEYWORDS)


def needs_comparison(question):
    text = f" {question.lower()} "
    return any(keyword in text for keyword in COMPARISON_KEYWORDS)


def _previous_period(period):
    month_match = re.fullmatch(r"month:(\d{4})-(\d{2})", period)
    if month_match:
        year = int(month_match.group(1))
        month = int(month_match.group(2))
        if month == 1:
            return f"month:{year - 1}-12"
        return f"month:{year}-{month - 1:02d}"

    year_match = re.fullmatch(r"year:(\d{4})", period)
    if year_match:
        return f"year:{int(year_match.group(1)) - 1}"

    return {
        "today": "yesterday",
        "this_week": "last_week",
        "this_month": "last_month",
        "this_year": "last_year",
    }.get(period)


def _comparison_base_period(question):
    text = question.lower()

    if "year to year" in text or "year over year" in text or "yoy" in text:
        explicit_period = normalize_period(question)
        if re.fullmatch(r"year:\d{4}", explicit_period):
            return explicit_period
        return "this_year"

    if "month to month" in text or "month over month" in text or "mom" in text:
        explicit_period = normalize_period(question)
        if re.fullmatch(r"month:\d{4}-\d{2}", explicit_period):
            return explicit_period
        return "this_month"

    return normalize_period(question)


def _format_number(value):
    if isinstance(value, int):
        return f"{value:,}"
    return value


def _compact_result(value):
    if isinstance(value, dict):
        return {
            key: _compact_result(item)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [
            _compact_result(item)
            for item in value
        ]

    return _format_number(value)


def _period_label(period):
    date_match = re.fullmatch(r"date:(\d{4})-(\d{2})-(\d{2})", period)
    if date_match:
        return date(
            int(date_match.group(1)),
            int(date_match.group(2)),
            int(date_match.group(3)),
        ).strftime("%B %d, %Y")

    month_match = re.fullmatch(r"month:(\d{4})-(\d{2})", period)
    if month_match:
        year = int(month_match.group(1))
        month = int(month_match.group(2))
        return date(year, month, 1).strftime("%B %Y")

    year_match = re.fullmatch(r"year:(\d{4})", period)
    if year_match:
        return year_match.group(1)

    return {
        "today": "today",
        "yesterday": "yesterday",
        "this_week": "this week",
        "last_week": "last week",
        "this_month": "this month",
        "last_month": "last month",
        "this_year": "this year",
        "last_year": "last year",
        "all_time": "all time",
    }.get(period, period)


def _scope_label(result):
    filters = result.get("filters") or {}
    parts = []

    if filters.get("sector"):
        parts.append(filters["sector"])

    if filters.get("category"):
        parts.append(filters["category"])

    if filters.get("item_description"):
        parts.append(filters["item_description"])

    if filters.get("payment_method"):
        parts.append(filters["payment_method"])

    if filters.get("income_expense"):
        parts.append(filters["income_expense"])

    if filters.get("farm_customer"):
        parts.append(filters["farm_customer"])

    return f" ({' / '.join(parts)})" if parts else ""


def _fast_answer(result):
    formula = result.get("formula")
    period = _period_label(result.get("period", "all_time")) + _scope_label(result)

    if formula == "sales_total":
        total = result["total_sales"]
        if total == 0:
            return f"Total sales for {period}: 0\nNo matching income data found."
        lines = [f"Total sales for {period}: {total:,}"]
        if "amount_received" in result:
            lines.append(f"Paid / received: {result['amount_received']:,}")
        if "outstanding_amount" in result:
            lines.append(f"Remained: {result['outstanding_amount']:,}")
        income_rows = result.get("transection_income_rows") or []
        if income_rows:
            lines.extend(["", "Transection Income"])
            for row in income_rows[:10]:
                lines.append(
                    f"{row.get('Date') or '-'} | {row.get('item') or '-'} | "
                    f"{int(row.get('amount') or 0):,} | {row.get('payment_method') or '-'}"
                )
        return "\n".join(lines)

    if formula == "expense_total":
        total = result["total_expense"]
        count = result.get("expense_count", 0)
        missing = result.get("missing_amount_count", 0)
        if total == 0:
            if count and missing:
                return (
                    f"Total expense for {period}: 0\n"
                    f"{count} expense row found, but {missing} row has empty Amount. Please add the amount in NocoDB."
                )
            return f"Total expense for {period}: 0\nNo matching expense data found."
        return f"Total expense for {period}: {total:,}"

    if formula == "gross_profit":
        return (
            f"Gross profit for {period}: {result['gross_profit']:,}\n"
            f"Income: {result['income']:,}\n"
            f"Expense: {result['expense']:,}"
        )

    if formula == "kpi_overview":
        lines = [
            f"KPI overview for {period}",
            f"Income: {result['total_income']:,}",
            f"Expense: {result['total_expense']:,}",
            f"Net profit: {result['net_profit']:,}",
            f"Profit margin: {result['profit_margin_percent']}%",
        ]
        if "amount_received" in result:
            lines.append(f"Received: {result['amount_received']:,}")
        if "outstanding_amount" in result:
            lines.append(f"Outstanding / unpaid: {result['outstanding_amount']:,}")
        return "\n".join(lines)

    if formula == "cash_flow":
        lines = [
            f"Cash flow for {period}",
            f"Inflow: {result['total_inflow']:,}",
            f"Outflow: {result['total_outflow']:,}",
            f"Net cash flow: {result['net_cash_flow']:,}",
        ]
        for row in result["by_payment_method"]:
            lines.append(
                f"{row['payment_method']}: in {row['inflow']:,}, out {row['outflow']:,}, net {row['net_cash_flow']:,}"
            )
        return "\n".join(lines)

    if formula == "sector_summary":
        lines = [f"Sector summary for {period}"]
        if not result["sectors"]:
            return f"Sector summary for {period}: no matching data found."
        for row in result["sectors"]:
            lines.append(
                f"{row['sector']}: income {row['income']:,}, expense {row['expense']:,}, profit {row['profit']:,}"
            )
        return "\n".join(lines)

    if formula == "category_summary":
        filters = result.get("filters") or {}
        if filters.get("sector") == "Farm" and filters.get("income_expense") == "Income":
            customers = sorted(
                result.get("categories") or [],
                key=lambda row: int(row.get("income") or row.get("total_amount") or row.get("amount") or 0),
                reverse=True,
            )
            total_sales = int(result.get("total_income") or 0)
            total_paid = sum(int(row.get("amount_received", row.get("income", 0)) or 0) for row in customers)
            total_outstanding = sum(int(row.get("outstanding_amount") or 0) for row in customers)
            lines = [
                f"Farm Income Summary for {period}",
                "",
                "KPI Summary",
                f"Total Sales: {total_sales:,}",
                f"Total Paid: {total_paid:,}",
                f"Total Outstanding: {total_outstanding:,}",
                "",
                "Top Customers by Revenue",
            ]
            if not customers:
                lines.append("No customer sales found.")
            for index, row in enumerate(customers[:10], start=1):
                sales = int(row.get("income") or row.get("total_amount") or row.get("amount") or 0)
                paid = int(row.get("amount_received", sales) or 0)
                outstanding = int(row.get("outstanding_amount") or 0)
                lines.append(
                    f"{index}. {row.get('customer_name') or row.get('category') or row.get('item') or '-'} | "
                    f"Total Sales: {sales:,} | Paid: {paid:,} | Outstanding: {outstanding:,}"
                )
            lines.extend([
                "",
                "Customer Collection Status",
                "Customer Name | Total Sales | Paid Amount | Outstanding Amount",
            ])
            for row in customers[:20]:
                sales = int(row.get("income") or row.get("total_amount") or row.get("amount") or 0)
                paid = int(row.get("amount_received", sales) or 0)
                outstanding = int(row.get("outstanding_amount") or 0)
                lines.append(
                    f"{row.get('customer_name') or row.get('category') or row.get('item') or '-'} | "
                    f"{sales:,} | {paid:,} | {outstanding:,}"
                )
            return "\n".join(lines)

        lines = [f"Category summary for {period}"]
        if not result["categories"]:
            return f"Category summary for {period}: no matching data found."
        for row in result["categories"]:
            if row.get("customer_name"):
                label = f"{row['sector']} customer name {row['customer_name']}"
            else:
                label = f"{row['sector']} / {row['category']}"
            line = (
                f"{label}: income {row['income']:,}, "
                f"expense {row['expense']:,}, net {row['net']:,}, rows {row['transaction_count']:,}"
            )
            if "amount_received" in row:
                line += f", paid {row['amount_received']:,}"
            if "outstanding_amount" in row:
                line += f", remained {row['outstanding_amount']:,}"
            lines.append(line)
        return "\n".join(lines)

    if formula == "top_expenses":
        if not result["expenses"]:
            return f"Top expenses for {period}: no matching expense data found."
        lines = [f"Top expenses for {period}"]
        for row in result["expenses"]:
            lines.append(
                f"{row['amount']:,} - {row['Date']} - {row['item']} ({row['sector']} / {row['category']}, {row['payment_method']})"
            )
        return "\n".join(lines)

    if formula == "top_income":
        if not result["income"]:
            return f"Top income for {period}: no matching income data found."
        lines = [f"Top income for {period}"]
        for index, row in enumerate(result["income"], start=1):
            if "total_amount" in row:
                name = row.get("customer_name") or row["item"]
                lines.append(
                    f"{index}. {name} ({row['sector']} / {row['category']})\n"
                    f"Total sales: {row['total_amount']:,}\n"
                    f"Paid / received: {row.get('amount_received', 0):,}\n"
                    f"Remained: {row.get('outstanding_amount', 0):,}\n"
                    f"Invoices: {row.get('invoice_count', 0):,}"
                )
                continue
            lines.append(
                f"{row['amount']:,} - {row['Date']} - {row['item']} ({row['sector']} / {row['category']}, {row['payment_method']})"
            )
        return "\n".join(lines)

    if formula == "list_transactions":
        if not result["transactions"]:
            return f"Transactions for {period}: no matching data found."
        lines = [f"Transactions for {period}"]
        for row in result["transactions"]:
            line = (
                f"{row['Date']} - Transaction {row.get('id', '-')}\n"
                f"Type: {row['income_expense']}\n"
                f"Category: {row['category']}\n"
                f"Item: {row['item'] or '-'}\n"
                f"Amount: {row['amount']:,}\n"
                f"Payment: {row['payment_method']}"
            )
            if row.get("note"):
                line += f"\nNote: {row['note']}"
            lines.append(line)
        return "\n".join(lines)

    if formula == "sotephwar_transection_summary":
        customers = sorted(
            result.get("customers") or [],
            key=lambda row: int(row.get("total_amount") or row.get("amount") or 0),
            reverse=True,
        )
        lines = [
            f"Sote Phwar Income Summary for {period}",
            "",
            "KPI Summary",
            f"Total Sales: {result['total_amount']:,}",
            f"Total Paid: {result['amount_received']:,}",
            f"Total Outstanding: {result['outstanding_amount']:,}",
            "",
            "Top Customers by Revenue",
        ]
        if not customers:
            lines.append("No customer sales found.")
        for index, row in enumerate(customers[:10], start=1):
            lines.append(
                f"{index}. {row.get('customer_name') or row.get('item') or '-'} | "
                f"Total Sales: {int(row.get('total_amount') or row.get('amount') or 0):,} | "
                f"Paid: {int(row.get('amount_received') or 0):,} | "
                f"Outstanding: {int(row.get('outstanding_amount') or 0):,}"
            )
        lines.extend([
            "",
            "Customer Collection Status",
            "Customer Name | Total Sales | Paid Amount | Outstanding Amount",
        ])
        for row in customers[:20]:
            lines.append(
                f"{row.get('customer_name') or row.get('item') or '-'} | "
                f"{int(row.get('total_amount') or row.get('amount') or 0):,} | "
                f"{int(row.get('amount_received') or 0):,} | "
                f"{int(row.get('outstanding_amount') or 0):,}"
            )
        return "\n".join(lines)

    if formula == "sotephwar_transection_monthly_summary":
        if not result["months"]:
            return f"Sotephwar_Transection month-by-month income for {period}: no matching data found."
        lines = [f"Sotephwar_Transection month-by-month income for {period}"]
        for row in result["months"]:
            lines.append(
                f"{row['month']}: total {row['total_amount']:,}, "
                f"received {row['amount_received']:,}, outstanding {row['outstanding_amount']:,}, "
                f"invoices {row['invoice_count']:,}"
            )
        return "\n".join(lines)

    if formula == "sotephwar_transection_top":
        if not result["invoices"]:
            return f"Top invoices from Sotephwar_Transection for {period}: no matching data found."
        lines = [f"Top invoices from Sotephwar_Transection for {period}"]
        for row in result["invoices"]:
            lines.append(
                f"{row['total_amount']:,} - {row['invoice_date']} - {row['customer_name']} - {row['item']} "
                f"(received {row['amount_received']:,}, outstanding {row['outstanding_amount']:,})"
            )
        return "\n".join(lines)

    if formula == "sotephwar_transection_list":
        if not result["invoices"]:
            label = "Unpaid invoices" if result.get("unpaid_only") else "Invoices"
            return f"{label} from Sotephwar_Transection for {period}: no matching data found."
        label = "Unpaid invoices" if result.get("unpaid_only") else "Invoices"
        lines = [f"{label} from Sotephwar_Transection for {period}"]
        for row in result["invoices"]:
            line = (
                f"{row['invoice_date']} - {row['customer_name']} - {row['item']} - total {row['total_amount']:,}, "
                f"received {row['amount_received']:,}, outstanding {row['outstanding_amount']:,}"
            )
            if row.get("note") or result.get("include_note"):
                line += f"\nNote: {row.get('note') or '-'}"
            lines.append(line)
        return "\n".join(lines)

    if formula == "sotephwar_transection_quantity":
        return (
            f"Sotephwar_Transection quantity for {period}\n"
            f"Item: {result['item']}\n"
            f"Quantity sold: {result['quantity']:,}\n"
            f"Invoices: {result['invoice_count']:,}\n"
            f"Total amount: {result['total_amount']:,}\n"
            f"Amount received: {result['amount_received']:,}\n"
            f"Outstanding: {result['outstanding_amount']:,}"
        )

    if formula == "sotephwar_transection_customer":
        customer = result.get("customer") or "matching customer"
        customer_match = result.get("customer_match") or {}
        if customer_match.get("confidence") == "ambiguous":
            candidates = customer_match.get("candidates") or []
            lines = [
                "Sotephwar_Transection customer search is too broad.",
                f"Search text: {customer_match.get('query') or '-'}",
                "Please use the full customer name.",
            ]
            if candidates:
                lines.append("Possible matches:")
                lines.extend(f"- {candidate}" for candidate in candidates[:8])
            return "\n".join(lines)
        if not result["invoices"]:
            label = "unpaid vouchers" if result.get("unpaid_only") else "vouchers"
            return f"Sotephwar_Transection {label} for {customer}: no matching data found."
        label = "unpaid vouchers" if result.get("unpaid_only") else "vouchers"
        lines = [f"Sotephwar_Transection {label} for {customer}"]
        for row in result["invoices"]:
            line = (
                f"{row['invoice_date']} - Voucher {row['invoice_number']} - {row['customer_name']}\n"
                f"Item: {row['item']}\n"
                f"Quantity: {row['quantity']:,}\n"
                f"Total amount: {row['total_amount']:,}\n"
                f"Amount received: {row['amount_received']:,}\n"
                f"Amount remained: {row['outstanding_amount']:,}"
            )
            if row.get("note") or result.get("include_note"):
                line += f"\nNote: {row.get('note') or '-'}"
            lines.append(line)
        return "\n\n".join(lines)

    if formula == "sotephwar_payment_update":
        if not result.get("updated"):
            missing = ", ".join(result.get("missing") or [])
            return (
                "Sote Phwar payment was not updated.\n"
                f"Missing: {missing}\n"
                "Use: Sote Phwar voucher NUMBER got 400000 kyats received date YYYY-MM-DD"
            )
        lines = [
            "Sote Phwar payment updated",
            f"Voucher: {result['invoice_number']}",
            f"Payment received: {result['payment_amount']:,}",
            f"Received date note: {result['received_date']}",
        ]
        for row in result["invoices"]:
            lines.append(
                f"{row['invoice_date']} - {row['customer_name']} - {row['item']}\n"
                f"Total: {row['total_amount']:,}\n"
                f"Received before: {row['previous_amount_received']:,}\n"
                f"Received now: {row['amount_received']:,}\n"
                f"Outstanding: {row['outstanding_amount']:,}\n"
                f"Note: {row.get('note') or '-'}"
            )
        return "\n\n".join(lines)

    if formula == "sotephwar_inventory_stock":
        if not result["stock"]:
            return "Sotephwar_Inventory current stock: no matching stock found."
        lines = ["Sotephwar_Inventory current stock"]
        if result.get("store"):
            lines.append(f"Store: {result['store']}")
        if result.get("product"):
            lines.append(f"Product: {result['product']}")
        for row in result["stock"]:
            lines.append(f"- {row['store']} / {row['product']}: {row['stock_qty']:,}")
        return "\n".join(lines)

    if formula == "sotephwar_inventory_movement_summary":
        if not result["movements"]:
            return f"Sotephwar_Inventory movement summary for {period}: no matching data found."
        lines = [f"Sotephwar_Inventory movement summary for {period}"]
        if result.get("store"):
            lines.append(f"Store: {result['store']}")
        if result.get("product"):
            lines.append(f"Product: {result['product']}")
        if result.get("movement_type"):
            lines.append(f"Type: {result['movement_type']}")
        for row in result["movements"]:
            lines.append(
                f"- {row['type']} / {row['product']}: {row['quantity']:,} "
                f"({row['movement_count']:,} rows)"
            )
        return "\n".join(lines)

    if formula == "sotephwar_inventory_list":
        if not result["movements"]:
            return f"Sotephwar_Inventory movements for {period}: no matching data found."
        lines = [f"Sotephwar_Inventory movements for {period}"]
        if result.get("store"):
            lines.append(f"Store: {result['store']}")
        if result.get("product"):
            lines.append(f"Product: {result['product']}")
        if result.get("movement_type"):
            lines.append(f"Type: {result['movement_type']}")
        for row in result["movements"]:
            line = (
                f"{row['date']} - {row['type']} - {row['product']}\n"
                f"From: {row['from_store']} -> To: {row['to_store']}\n"
                f"Qty: {row['quantity']:,}"
            )
            if row.get("note"):
                line += f"\nNote: {row['note']}"
            lines.append(line)
        return "\n\n".join(lines)

    if formula == "financial_obligation_summary":
        if not result["summary"]:
            return "Financial_Obligations summary: no matching data found."
        lines = ["Financial_Obligations summary"]
        if result.get("category"):
            lines.append(f"Category filter: {result['category']}")
        if result.get("status"):
            lines.append(f"Status filter: {result['status']}")
        for row in result["summary"]:
            lines.append(
                f"- {row['category'] or '-'} / {row['status'] or '-'}: "
                f"{row['amount']:,} ({row['obligation_count']:,} rows), next due {row['next_due_date'] or '-'}"
            )
        return "\n".join(lines)

    if formula == "financial_obligation_due":
        if not result["obligations"]:
            return f"Financial_Obligations due in next {result['days']} days: no matching data found."
        lines = [f"Financial_Obligations due in next {result['days']} days"]
        for row in result["obligations"]:
            days = row.get("days_until_due")
            if days is None:
                due_label = "-"
            elif days < 0:
                due_label = f"{abs(days)} days overdue"
            elif days == 0:
                due_label = "due today"
            else:
                due_label = f"due in {days} days"
            line = (
                f"{row['next_due_date']} ({due_label}) - {row['creditor']} - {row['amount']:,}\n"
                f"{row['category']} / {row['subcategory'] or '-'} / {row['frequency'] or '-'} / {row['status']}"
            )
            if row.get("notes"):
                line += f"\nNotes: {row['notes']}"
            lines.append(line)
        return "\n\n".join(lines)

    if formula == "financial_obligation_list":
        if not result["obligations"]:
            return "Financial_Obligations list: no matching data found."
        lines = ["Financial_Obligations list"]
        if result.get("category"):
            lines.append(f"Category filter: {result['category']}")
        if result.get("creditor"):
            lines.append(f"Creditor filter: {result['creditor']}")
        for row in result["obligations"]:
            line = (
                f"{row['next_due_date'] or '-'} - {row['creditor']} - {row['amount']:,}\n"
                f"{row['category']} / {row['subcategory'] or '-'} / {row['frequency'] or '-'} / {row['status']}"
            )
            if row.get("notes"):
                line += f"\nNotes: {row['notes']}"
            lines.append(line)
        return "\n\n".join(lines)

    if formula == "financial_obligation_insert":
        if not result.get("inserted"):
            missing = ", ".join(result.get("missing") or [])
            return (
                "Financial obligation was not inserted.\n"
                f"Missing: {missing}\n"
                "Use: add financial obligation creditor NAME amount 1000000 category Loan "
                "subcategory Investor Loan frequency Monthly start 2026-06-03 next due 2026-07-03 "
                "status Active notes optional text"
            )
        row = result["obligation"]
        return (
            "Financial obligation inserted\n"
            f"ID: {row['id']}\n"
            f"Creditor: {row['creditor']}\n"
            f"Amount: {row['amount']:,}\n"
            f"Category: {row['category']} / {row['subcategory'] or '-'}\n"
            f"Frequency: {row['frequency'] or '-'}\n"
            f"Next due: {row['next_due_date']}\n"
            f"Status: {row['status']}"
        )

    return None


def _sotephwar_sector_row(sector_summary):
    for row in (sector_summary or {}).get("sectors") or []:
        if row.get("sector") == "Sote Phwar":
            return row
    return {}


def _combined_kpi(period, kpi, sector_summary, sotephwar_summary):
    sotephwar_sector = _sotephwar_sector_row(sector_summary)
    main_sotephwar_income = _number(sotephwar_sector.get("income", 0))
    sotephwar_invoice_income = _number(sotephwar_summary.get("total_amount", 0))

    total_income = (
        _number(kpi.get("total_income", 0))
        - main_sotephwar_income
        + sotephwar_invoice_income
    )
    total_expense = _number(kpi.get("total_expense", 0))
    net_profit = total_income - total_expense
    margin = round((net_profit / total_income) * 100, 2) if total_income else 0

    return {
        "formula": "combined_kpi_overview",
        "period": period,
        "total_income": total_income,
        "total_expense": total_expense,
        "net_profit": net_profit,
        "profit_margin_percent": margin,
        "sources": {
            "transection_income_excluding_sotephwar": _number(kpi.get("total_income", 0)) - main_sotephwar_income,
            "sotephwar_transection_total_amount": sotephwar_invoice_income,
            "transection_expense": total_expense,
        },
        "note": (
            "Sote Phwar income comes from Sotephwar_Transection, so it does not need "
            "to be duplicated in Transection."
        ),
    }


def _analysis_context(question):
    period = normalize_period(question)
    kpi = run_formula("kpi_overview", question)
    sector_summary = run_formula("sector_summary", question)
    sotephwar_summary = FORMULAS["sotephwar_transection_summary"](period)
    return {
        "period": period,
        "kpi": kpi,
        "combined_kpi": _combined_kpi(period, kpi, sector_summary, sotephwar_summary),
        "cash_flow": run_formula("cash_flow", question),
        "sector_summary": sector_summary,
        "category_summary": run_formula("category_summary", question),
        "top_expenses": run_formula("top_expenses", question),
        "sotephwar_transection": sotephwar_summary,
    }


def _combined_kpi_for_period(period):
    kpi = FORMULAS["kpi_overview"](period)
    sector_summary = FORMULAS["sector_summary"](period)
    sotephwar_summary = FORMULAS["sotephwar_transection_summary"](period)
    return _combined_kpi(period, kpi, sector_summary, sotephwar_summary)


def _comparison_context(question):
    current_period = _comparison_base_period(question)
    previous_period = _previous_period(current_period)

    if not previous_period:
        current_period = "this_month"
        previous_period = "last_month"

    current = _combined_kpi_for_period(current_period)
    previous = _combined_kpi_for_period(previous_period)

    income_change = current["total_income"] - previous["total_income"]
    expense_change = current["total_expense"] - previous["total_expense"]
    profit_change = current["net_profit"] - previous["net_profit"]

    return {
        "comparison": {
            "current_period": _period_label(current_period),
            "previous_period": _period_label(previous_period),
            "current": current,
            "previous": previous,
            "change": {
                "income": income_change,
                "income_percent": _percent_change(income_change, previous["total_income"]),
                "expense": expense_change,
                "expense_percent": _percent_change(expense_change, previous["total_expense"]),
                "net_profit": profit_change,
                "net_profit_percent": _percent_change(profit_change, previous["net_profit"]),
                "profit_margin_points": round(
                    current["profit_margin_percent"] - previous["profit_margin_percent"],
                    2,
                ),
            },
        }
    }


def _percent_change(change, previous_value):
    if previous_value == 0:
        return None
    return round((change / previous_value) * 100, 2)


def _number(value):
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        return int(value.replace(",", ""))
    return int(value or 0)


def _fallback_analysis_answer(context):
    kpi = context.get("combined_kpi") or context.get("kpi") or {}
    cash_flow = context.get("cash_flow") or {}
    categories = (context.get("category_summary") or {}).get("categories") or []
    top_expenses = (context.get("top_expenses") or {}).get("expenses") or []

    income = _number(kpi.get("total_income", 0))
    expense = _number(kpi.get("total_expense", 0))
    profit = _number(kpi.get("net_profit", 0))
    margin = kpi.get("profit_margin_percent", 0)

    comment = (
        f"Comment: The business is currently running at a loss. "
        f"Income is {income:,}, but expense is {expense:,}, so net profit is {profit:,} "
        f"with {margin}% margin."
        if profit < 0
        else (
            f"Comment: The business is profitable. Income is {income:,}, expense is {expense:,}, "
            f"and net profit is {profit:,} with {margin}% margin."
        )
    )

    expense_categories = [
        row
        for row in categories
        if _number(row.get("expense", 0)) > 0
    ][:3]

    lines = [comment, "", "Risks / causes:"]

    if profit < 0:
        lines.append("- Expenses are higher than income, so cash pressure is high.")

    for row in expense_categories:
        lines.append(
            f"- {row['category']} is a major cost: {_number(row['expense']):,}."
        )

    if top_expenses:
        row = top_expenses[0]
        lines.append(
            f"- Biggest single expense is {row['item']}: {_number(row['amount']):,}."
        )

    cash_methods = cash_flow.get("by_payment_method") or []
    for method in cash_methods:
        net_cash = _number(method.get("net_cash_flow", 0))
        if net_cash < 0:
            lines.append(
                f"- {method['payment_method']} cash flow is negative: {net_cash:,}."
            )
            break

    lines.extend(["", "Recommended actions:"])
    lines.append("- Review the top 3 expense categories first and set a spending limit for each.")
    lines.append("- Check the biggest single expense and confirm it is correct and necessary.")
    lines.append("- Push income collection before adding more farm spending.")
    lines.append("- Separate cash and Pay balances because one payment method may look healthy while cash is negative.")

    return "\n".join(lines)


def _answer_with_ai(question, context):
    display_context = _compact_result(context)
    analysis_prompt = f"""
You are Bigshot Lady Bot, a concise local business advisor.

Question:
{question}

Real calculated data from PostgreSQL/NocoDB:
{json.dumps(display_context, indent=2, default=str)}

Answer style:
- If the user asks to analyze, comment, suggest, recommend, explain, or give advice, write business commentary, not only KPI numbers.
- Start with a short business comment about what the data means.
- Then give 2-4 risks or likely causes visible from the data.
- Then give 2-4 practical recommended actions.
- Use combined_kpi as the main KPI because it combines Transection with Sotephwar_Transection.
- Use cash flow, sector, category, top expense, and Sotephwar_Transection data as supporting evidence.
- Treat Sotephwar_Transection as the source of truth for Sote Phwar income; do not require duplicated Sote Phwar income rows in Transection.
- Treat Financial_Obligations as reminder data only; do not include it in KPI, profit, income, expense, or statistics calculations.
- Mention exact numbers only where they support the comment.
- Do not return a KPI-only answer unless the user specifically asks only for KPI.
- Do not use "$" or any currency symbol; show amounts as plain numbers.
- Do not say changing payment method reduces expense. Payment method only affects cash-flow tracking.
- Do not recommend automation, staff cuts, supplier discounts, or percentage savings unless the data directly supports it.
- Do not invent data outside the provided context.
- Keep the answer short enough for Telegram.
"""

    try:
        ai_answer = ask_ai(analysis_prompt).strip()
        if ai_answer:
            return ai_answer
    except Exception:
        pass

    if "kpi" in context:
        return _fallback_analysis_answer(context)

    return json.dumps(display_context, indent=2, default=str)


def answer_question(question):
    formula_name = choose_formula(question)

    if formula_name == "comparison":
        return _answer_with_ai(question, _comparison_context(question))

    if formula_name == "analysis":
        return _answer_with_ai(question, _analysis_context(question))

    raw_result = run_formula(formula_name, question)

    if formula_name in FAST_FORMULAS:
        answer = _fast_answer(raw_result)
        if answer:
            return answer

    display_result = _compact_result(raw_result)

    return _answer_with_ai(question, {
        "formula_used": formula_name,
        "result": display_result,
    })
