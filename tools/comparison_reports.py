import json

from tools.bi_periods import legacy_period, period_label, relative_period
from tools.formula_engine import category_summary
from tools.ollama_client import ask_ai


def _money(value):
    return f"{int(value or 0):,}"


def _percent_change(change, previous):
    previous = int(previous or 0)
    if not previous:
        return None
    return round((int(change or 0) / previous) * 100, 2)


def _category_key(row):
    sector = row.get("sector") or ""
    category = row.get("category") or "-"
    return sector, category


BUSINESS_CONFIG = {
    "sote_phwar": {
        "title": "Sote Phwar",
        "sector": "Sote Phwar",
        "aliases": ("sote phwar", "sotephwar"),
    },
    "farm": {
        "title": "Farm",
        "sector": "Farm",
        "aliases": ("farm",),
    },
}


def _expense_summary(period_value, label, sector):
    result = category_summary(
        legacy_period(relative_period(period_value)),
        {"sector": sector, "income_expense": "Expense"},
    )
    categories = result.get("categories") or []
    total = int(result.get("total_expense") or sum(int(row.get("expense") or 0) for row in categories) or 0)
    paid = int(result.get("amount_received") or 0)
    if not paid:
        paid = sum(int(row.get("amount_received") or 0) for row in categories)
    if not paid and total:
        paid = total
    outstanding = int(result.get("outstanding_amount") or 0)
    if not outstanding:
        outstanding = sum(int(row.get("outstanding_amount") or 0) for row in categories)
    return {
        "period": period_value,
        "label": label,
        "total_expense": total,
        "paid": paid,
        "outstanding": outstanding,
        "transaction_count": int(result.get("transaction_count") or sum(int(row.get("transaction_count") or 0) for row in categories)),
        "categories": categories,
    }


def _category_rows(previous, current):
    previous_by_category = {
        _category_key(row): int(row.get("expense") or abs(row.get("net", 0)) or 0)
        for row in previous.get("categories") or []
    }
    current_by_category = {
        _category_key(row): int(row.get("expense") or abs(row.get("net", 0)) or 0)
        for row in current.get("categories") or []
    }
    rows = []
    current_total = int(current.get("total_expense") or 0)
    for sector, category in sorted(set(previous_by_category) | set(current_by_category)):
        previous_amount = previous_by_category.get((sector, category), 0)
        current_amount = current_by_category.get((sector, category), 0)
        change = current_amount - previous_amount
        contribution = round((current_amount / current_total) * 100, 2) if current_total else 0
        rows.append({
            "sector": sector or "-",
            "category": category,
            "previous_amount": previous_amount,
            "current_amount": current_amount,
            "change": change,
            "change_percent": _percent_change(change, previous_amount),
            "current_contribution_percent": contribution,
            "flag_change_over_20_percent": (
                previous_amount > 0
                and abs(change) > 0
                and abs(_percent_change(change, previous_amount) or 0) > 20
            ),
            "flag_zero_current_previous_spending": current_amount == 0 and previous_amount > 0,
            "flag_new_current_spending": previous_amount == 0 and current_amount > 0,
        })
    return sorted(rows, key=lambda row: abs(row["change"]), reverse=True)


def _kpi_summary(previous, current, rows):
    change = current["total_expense"] - previous["total_expense"]
    increases = [row for row in rows if row["change"] > 0]
    decreases = [row for row in rows if row["change"] < 0]
    largest_categories = sorted(rows, key=lambda row: row["current_amount"], reverse=True)
    flagged_changes = [
        row for row in rows
        if row["flag_change_over_20_percent"]
    ]
    zero_current = [
        row for row in rows
        if row["flag_zero_current_previous_spending"]
    ]
    new_spending = [
        row for row in rows
        if row["flag_new_current_spending"]
    ]
    top_category = largest_categories[0] if largest_categories else {}
    return {
        "current_total_expense": current["total_expense"],
        "previous_total_expense": previous["total_expense"],
        "expense_change": change,
        "expense_change_percent": _percent_change(change, previous["total_expense"]),
        "current_transaction_count": current["transaction_count"],
        "previous_transaction_count": previous["transaction_count"],
        "transaction_count_change": current["transaction_count"] - previous["transaction_count"],
        "category_count_current": len([row for row in rows if row["current_amount"] > 0]),
        "category_count_previous": len([row for row in rows if row["previous_amount"] > 0]),
        "largest_category": top_category.get("category"),
        "largest_category_amount": top_category.get("current_amount", 0),
        "largest_category_contribution_percent": top_category.get("current_contribution_percent", 0),
        "increase_count": len(increases),
        "decrease_count": len(decreases),
        "over_20_percent_change_count": len(flagged_changes),
        "zero_current_previous_spending_count": len(zero_current),
        "new_current_spending_count": len(new_spending),
    }


def _analytics(previous, current, rows):
    increases = sorted(
        (row for row in rows if row["change"] > 0),
        key=lambda row: row["change"],
        reverse=True,
    )
    decreases = sorted(
        (row for row in rows if row["change"] < 0),
        key=lambda row: row["change"],
    )
    largest_categories = sorted(rows, key=lambda row: row["current_amount"], reverse=True)
    return {
        "top_5_increases": increases[:5],
        "top_5_decreases": decreases[:5],
        "largest_expense_categories": largest_categories[:5],
        "percentage_contribution_by_category": [
            {
                "sector": row["sector"],
                "category": row["category"],
                "current_amount": row["current_amount"],
                "current_contribution_percent": row["current_contribution_percent"],
            }
            for row in largest_categories
            if row["current_amount"] > 0
        ],
        "categories_over_20_percent_change": [
            row for row in rows if row["flag_change_over_20_percent"]
        ],
        "zero_current_value_with_previous_spending": [
            row for row in rows if row["flag_zero_current_previous_spending"]
        ],
        "new_current_spending_categories": [
            row for row in rows if row["flag_new_current_spending"]
        ],
        "kpi_summary_statistics": _kpi_summary(previous, current, rows),
    }


def _fallback_comment(business_title, previous, current, analytics):
    kpi = analytics["kpi_summary_statistics"]
    change = kpi["expense_change"]
    change_percent = kpi["expense_change_percent"]
    direction = "increased" if change > 0 else "decreased" if change < 0 else "stayed flat"
    percent_text = f" ({change_percent}%)" if change_percent is not None else ""
    lines = [
        f"Business comment: {business_title} expenses {direction} by {_money(abs(change))}{percent_text}, from {_money(previous['total_expense'])} to {_money(current['total_expense'])}.",
        "",
        "Key signals:",
    ]
    if analytics["top_5_increases"]:
        for row in analytics["top_5_increases"][:2]:
            percent = f" ({row['change_percent']}%)" if row["change_percent"] is not None else ""
            lines.append(f"- Cost driver: {row['category']} increased by {_money(row['change'])}{percent}.")
    if analytics["zero_current_value_with_previous_spending"]:
        row = analytics["zero_current_value_with_previous_spending"][0]
        lines.append(f"- Missing transaction risk: {row['category']} had {_money(row['previous_amount'])} last period but 0 this period.")
    if analytics["largest_expense_categories"]:
        row = analytics["largest_expense_categories"][0]
        lines.append(
            f"- Largest current cost: {row['category']} is {_money(row['current_amount'])}, "
            f"{row['current_contribution_percent']}% of spending."
        )
    if not lines[-1].startswith("-"):
        lines.append("- No category movement was found for the selected periods.")
    lines.extend(["", "Recommended actions:"])
    if analytics["top_5_increases"]:
        row = analytics["top_5_increases"][0]
        lines.append(f"- Check what created the {_money(row['change'])} increase in {row['category']} and approve only if it matches operations.")
    if analytics["zero_current_value_with_previous_spending"]:
        row = analytics["zero_current_value_with_previous_spending"][0]
        lines.append(f"- Confirm whether {row['category']} truly stopped or whether this month's transaction is missing.")
    if analytics["largest_expense_categories"]:
        row = analytics["largest_expense_categories"][0]
        lines.append(f"- Put management control on {row['category']} first because it is the biggest cost share.")
    else:
        lines.append("- No specific action is required from the category data.")
    return "\n".join(lines)


def _ai_comment(question, business_title, previous, current, rows, analytics):
    prompt = f"""
You are Bigshot Lady Bot, a concise local business consultant.

Question:
{question}

Calculated {business_title} expense comparison:
{json.dumps({
    "previous_period": previous,
    "current_period": current,
    "analytics": analytics,
    "raw_category_comparison": rows,
}, indent=2, default=str)}

Answer style:
- Do not return JSON, code, markdown tables, or structured intent.
- Explain the business implications of the largest changes instead of repeating totals.
- Focus on cost drivers, missing transactions, operational risks, spending anomalies, and management actions.
- Mention totals only when they support a specific implication.
- Do not use generic advice such as "review transactions" unless a specific category, amount, or anomaly is named.
- Start with one short business comment about the main cost driver or anomaly.
- Then give 2-4 key signals from the calculated analytics.
- Then give 2-4 practical actions tied to exact categories or flagged anomalies.
- Use exact numbers only where useful.
- Do not invent causes outside the data.
- Keep it short enough for Telegram.
"""
    try:
        answer = ask_ai(prompt, timeout=120).strip()
        if answer:
            return answer
    except Exception:
        pass
    return _fallback_comment(business_title, previous, current, analytics)


def expense_month_comparison(question, business):
    config = BUSINESS_CONFIG[business]
    business_title = config["title"]
    previous = _expense_summary("last_month", period_label(relative_period("last_month")), config["sector"])
    current = _expense_summary("this_month", period_label(relative_period("this_month")), config["sector"])
    rows = _category_rows(previous, current)
    analytics = _analytics(previous, current, rows)
    change = current["total_expense"] - previous["total_expense"]
    title = f"{business_title} - Expense - Month Comparison"
    payload = {
        "intent": {
            "business": business,
            "module": "expense",
            "report": "expense_comparison",
            "periods": ["last_month", "this_month"],
        },
        "title": title,
        "period_label": f"{previous['label']} vs {current['label']}",
        "result": {
            "formula": "expense_period_comparison",
            "_report_title": title,
            "_period_label": f"{previous['label']} vs {current['label']}",
            "periods": [
                {key: value for key, value in previous.items() if key != "categories"},
                {key: value for key, value in current.items() if key != "categories"},
            ],
            "categories": rows,
            "analytics": analytics,
            "raw_data": {
                "previous": previous,
                "current": current,
            },
            "total_change": change,
            "total_change_percent": _percent_change(change, previous["total_expense"]),
        },
    }
    payload["result"]["ai_comment"] = _ai_comment(question, business_title, previous, current, rows, analytics)
    return payload


def comparison_business(text):
    normalized = " ".join(text.lower().split())
    for business, config in BUSINESS_CONFIG.items():
        if any(alias in normalized for alias in config["aliases"]):
            return business
    return ""


def is_expense_month_comparison(text):
    normalized = " ".join(text.lower().split())
    return (
        "compare" in normalized
        and comparison_business(normalized) in BUSINESS_CONFIG
        and ("expense" in normalized or "expenses" in normalized)
        and "last month" in normalized
        and "this month" in normalized
    )
