import re

from tools.formula_engine import (
    cash_flow,
    category_summary,
    expense_total,
    kpi_overview,
    list_transactions,
    normalize_period,
    sales_total,
    sotephwar_inventory_movement_summary,
    sotephwar_inventory_stock,
    top_expenses,
    top_income,
)


BUSINESS_FILTERS = {
    "sote_phwar": {"sector": "Sote Phwar"},
    "farm": {"sector": "Farm"},
    "extension": {"sector": "SP Extension"},
}


ALLOWED_TOOLS = {
    "kpi",
    "revenue",
    "expense",
    "cash_flow",
    "top_customers",
    "top_expenses",
    "expense_detail",
    "income_detail",
    "inventory",
    "forecast",
    "comparison",
}


def business_from_question(question):
    text = " ".join(str(question).lower().split())
    if "sote phwar" in text or "sotephwar" in text:
        return "sote_phwar"
    if "farm" in text or "vegetable" in text or "crops" in text:
        return "farm"
    if "extension" in text:
        return "extension"
    return ""


def _filters(business="", income_expense=None, category=None):
    filters = dict(BUSINESS_FILTERS.get(business) or {})
    if income_expense:
        filters["income_expense"] = income_expense
    if category:
        filters["transaction_text_search"] = {"terms": _search_terms(category)}
    return filters


def _search_terms(text):
    return [
        token
        for token in re.sub(r"[^a-zA-Z0-9\s]", " ", str(text or "").lower()).split()
        if len(token) > 1
    ]


def _category_hint(question):
    text = str(question or "")
    lowered = text.lower()
    for marker in ("for ", "on ", "about "):
        if marker in lowered:
            candidate = text[lowered.rfind(marker) + len(marker):]
            candidate = re.sub(
                r"\b(this|last|month|year|week|today|yesterday|pdf|excel|report|detail|cost|expense|income)\b",
                " ",
                candidate,
                flags=re.IGNORECASE,
            )
            candidate = " ".join(candidate.split())
            if len(candidate) >= 3:
                return candidate
    return ""


def previous_period(period):
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
    }.get(period, "last_month")


def build_default_plan(question):
    text = f" {str(question).lower()} "
    business = business_from_question(question)
    period = normalize_period(question)

    if "forecast" in text:
        return [{"name": "forecast", "args": {"business": business, "period": period}}]
    if "inventory" in text or "stock" in text or "product" in text:
        return [{"name": "inventory", "args": {"business": business or "sote_phwar", "period": period}}]
    if "cash flow" in text or "cashflow" in text:
        return [{"name": "cash_flow", "args": {"business": business, "period": period}}]
    if "compare" in text or " versus " in text or " vs " in text:
        metric = "expense" if any(word in text for word in ("expense", "cost", "spend")) else "revenue"
        return [{"name": "comparison", "args": {"business": business, "period": period, "metric": metric}}]
    if "top customer" in text or "customer" in text or "revenue risk" in text:
        return [{"name": "top_customers", "args": {"business": business, "period": period}}]
    if "expense" in text or "cost" in text or "spend" in text:
        if "detail" in text or _category_hint(question):
            return [{"name": "expense_detail", "args": {"business": business, "period": period, "category": _category_hint(question)}}]
        return [{"name": "expense", "args": {"business": business, "period": period}}]
    if "income" in text or "sale" in text or "sales" in text or "revenue" in text:
        if "detail" in text:
            return [{"name": "income_detail", "args": {"business": business, "period": period, "category": _category_hint(question)}}]
        return [{"name": "revenue", "args": {"business": business, "period": period}}]
    return [
        {"name": "kpi", "args": {"business": business, "period": period}},
        {"name": "top_expenses", "args": {"business": business, "period": period}},
        {"name": "top_customers", "args": {"business": business, "period": period}},
    ]


def validate_plan(plan):
    if not isinstance(plan, list):
        return []
    valid = []
    for step in plan[:6]:
        if not isinstance(step, dict):
            continue
        name = step.get("name")
        args = step.get("args") or {}
        if name not in ALLOWED_TOOLS or not isinstance(args, dict):
            continue
        valid.append({"name": name, "args": args})
    return valid


def run_tool(name, args):
    args = args or {}
    business = args.get("business") or ""
    period = args.get("period") or "this_month"
    category = args.get("category") or ""

    if name == "kpi":
        return kpi_overview(period, _filters(business))
    if name == "revenue":
        return sales_total(period, _filters(business, "Income"))
    if name == "expense":
        return expense_total(period, _filters(business, "Expense"))
    if name == "cash_flow":
        return cash_flow(period, _filters(business))
    if name == "top_customers":
        return top_income(period, _filters(business, "Income"), limit=10)
    if name == "top_expenses":
        return top_expenses(period, _filters(business, "Expense"), limit=10)
    if name == "expense_detail":
        return list_transactions(period, _filters(business, "Expense", category), limit=20)
    if name == "income_detail":
        return list_transactions(period, _filters(business, "Income", category), limit=20)
    if name == "inventory":
        if business and business != "sote_phwar":
            return sotephwar_inventory_movement_summary(period)
        return sotephwar_inventory_stock()
    if name == "forecast":
        current = kpi_overview(period, _filters(business))
        previous = kpi_overview(previous_period(period), _filters(business))
        return {"formula": "forecast", "period": period, "current": current, "previous": previous}
    if name == "comparison":
        metric = args.get("metric") or "revenue"
        tool = sales_total if metric == "revenue" else expense_total
        income_expense = "Income" if metric == "revenue" else "Expense"
        current = tool(period, _filters(business, income_expense))
        previous = tool(previous_period(period), _filters(business, income_expense))
        return {"formula": "comparison", "metric": metric, "period": period, "current": current, "previous": previous}
    raise ValueError(f"Unsupported executive tool: {name}")


def execute_plan(plan):
    results = []
    for step in validate_plan(plan):
        results.append({
            "tool": step["name"],
            "args": step["args"],
            "result": run_tool(step["name"], step["args"]),
        })
    return results
