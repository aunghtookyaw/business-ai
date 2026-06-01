import json
import re
from datetime import date

from tools.formula_engine import (
    FORMULAS,
    choose_formula_by_keywords,
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

    return f" ({' / '.join(parts)})" if parts else ""


def _fast_answer(result):
    formula = result.get("formula")
    period = _period_label(result.get("period", "all_time")) + _scope_label(result)

    if formula == "sales_total":
        total = result["total_sales"]
        if total == 0:
            return f"Total sales for {period}: 0\nNo matching income data found."
        return f"Total sales for {period}: {total:,}"

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
        return (
            f"KPI overview for {period}\n"
            f"Income: {result['total_income']:,}\n"
            f"Expense: {result['total_expense']:,}\n"
            f"Net profit: {result['net_profit']:,}\n"
            f"Profit margin: {result['profit_margin_percent']}%"
        )

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
        lines = [f"Category summary for {period}"]
        if not result["categories"]:
            return f"Category summary for {period}: no matching data found."
        for row in result["categories"]:
            lines.append(
                f"{row['sector']} / {row['category']}: income {row['income']:,}, expense {row['expense']:,}, net {row['net']:,}, rows {row['transaction_count']:,}"
            )
        return "\n".join(lines)

    if formula == "top_expenses":
        if not result["expenses"]:
            return f"Top expenses for {period}: no matching expense data found."
        lines = [f"Top expenses for {period}"]
        for row in result["expenses"]:
            lines.append(
                f"{row['amount']:,} - {row['item']} ({row['sector']} / {row['category']}, {row['payment_method']})"
            )
        return "\n".join(lines)

    return None


def _analysis_context(question):
    period = normalize_period(question)
    return {
        "period": period,
        "kpi": run_formula("kpi_overview", question),
        "cash_flow": run_formula("cash_flow", question),
        "sector_summary": run_formula("sector_summary", question),
        "category_summary": run_formula("category_summary", question),
        "top_expenses": run_formula("top_expenses", question),
    }


def _comparison_context(question):
    current_period = _comparison_base_period(question)
    previous_period = _previous_period(current_period)

    if not previous_period:
        current_period = "this_month"
        previous_period = "last_month"

    current = FORMULAS["kpi_overview"](current_period)
    previous = FORMULAS["kpi_overview"](previous_period)

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


def _answer_with_ai(question, context):
    display_context = _compact_result(context)
    analysis_prompt = f"""
You are Bigshot Lady Bot, a concise local business advisor.

Question:
{question}

Real calculated data from PostgreSQL/NocoDB:
{json.dumps(display_context, indent=2, default=str)}

Answer style:
- Give direct suggestions and recommendations first when the user asks for advice.
- Use the real numbers as evidence.
- Do not only repeat KPI numbers.
- Do not invent data outside the provided context.
- Keep the answer short enough for Telegram.
"""

    try:
        ai_answer = ask_ai(analysis_prompt).strip()
        if ai_answer:
            return ai_answer
    except Exception:
        pass

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
