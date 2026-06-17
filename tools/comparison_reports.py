import json

from tools.bi_periods import legacy_period, period_label, relative_period
from tools.formula_engine import category_summary
from tools.openclaw_client import ask_ai


def _money(value):
    return f"{int(value or 0):,}"


def _percent_change(change, previous):
    previous = int(previous or 0)
    if not previous:
        return None
    return round((int(change or 0) / previous) * 100, 2)


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
        row.get("category") or "-": int(row.get("expense") or abs(row.get("net", 0)) or 0)
        for row in previous.get("categories") or []
    }
    current_by_category = {
        row.get("category") or "-": int(row.get("expense") or abs(row.get("net", 0)) or 0)
        for row in current.get("categories") or []
    }
    rows = []
    for category in sorted(set(previous_by_category) | set(current_by_category)):
        previous_amount = previous_by_category.get(category, 0)
        current_amount = current_by_category.get(category, 0)
        change = current_amount - previous_amount
        rows.append({
            "category": category,
            "previous_amount": previous_amount,
            "current_amount": current_amount,
            "change": change,
            "change_percent": _percent_change(change, previous_amount),
        })
    return sorted(rows, key=lambda row: abs(row["change"]), reverse=True)


def _fallback_comment(business_title, previous, current, change, change_percent, top_rows):
    direction = "increased" if change > 0 else "decreased" if change < 0 else "stayed flat"
    percent_text = f" ({change_percent}%)" if change_percent is not None else ""
    lines = [
        f"Business comment: {business_title} expenses {direction} by {_money(abs(change))}{percent_text}, from {_money(previous['total_expense'])} to {_money(current['total_expense'])}.",
        "",
        "Key signals:",
    ]
    if top_rows:
        for row in top_rows[:3]:
            row_direction = "up" if row["change"] > 0 else "down" if row["change"] < 0 else "flat"
            percent = f" ({row['change_percent']}%)" if row["change_percent"] is not None else ""
            lines.append(f"- {row['category']}: {row_direction} {_money(abs(row['change']))}{percent}.")
    else:
        lines.append("- No category movement was found for the selected periods.")
    lines.extend([
        "",
        "Recommended actions:",
        "- Review the categories with the largest increase first.",
        "- Check whether the increase came from one-time spending or repeated monthly cost.",
        "- Set next-month limits for the categories that moved up without matching income growth.",
    ])
    return "\n".join(lines)


def _ai_comment(question, business_title, previous, current, rows):
    change = current["total_expense"] - previous["total_expense"]
    change_percent = _percent_change(change, previous["total_expense"])
    top_rows = rows[:5]
    prompt = f"""
You are Bigshot Lady Bot, a concise local business consultant.

Question:
{question}

Calculated {business_title} expense comparison:
{json.dumps({
    "previous_period": previous,
    "current_period": current,
    "change": {
        "expense": change,
        "expense_percent": change_percent,
    },
    "top_category_changes": top_rows,
}, indent=2, default=str)}

Answer style:
- Do not return JSON, code, markdown tables, or structured intent.
- Start with one short business comment.
- Then give 2-4 key signals from the category movement.
- Then give 2-4 practical actions.
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
    return _fallback_comment(business_title, previous, current, change, change_percent, top_rows)


def expense_month_comparison(question, business):
    config = BUSINESS_CONFIG[business]
    business_title = config["title"]
    previous = _expense_summary("last_month", period_label(relative_period("last_month")), config["sector"])
    current = _expense_summary("this_month", period_label(relative_period("this_month")), config["sector"])
    rows = _category_rows(previous, current)
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
            "total_change": change,
            "total_change_percent": _percent_change(change, previous["total_expense"]),
        },
    }
    payload["result"]["ai_comment"] = _ai_comment(question, business_title, previous, current, rows)
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
