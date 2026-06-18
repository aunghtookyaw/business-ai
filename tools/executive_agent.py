import json
import re

from tools.executive_reports import format_executive_report
from tools.executive_tools import build_default_plan, execute_plan, validate_plan
from tools.openclaw_client import ask_ai


PLANNER_PROMPT = """
You are BigShot Intelligence, the Chief Financial Officer (CFO), Business Analyst, and Strategic Advisor for BigShot Company Limited.

Your responsibility is to transform raw business data into actionable business intelligence for the CEO, management team, investors, and department managers.

Return only valid JSON with this shape:
{"tools":[{"name":"tool_name","args":{"business":"sote_phwar|farm|extension|", "period":"this_month"}}]}

Allowed tools:
- kpi
- revenue
- expense
- cash_flow
- top_customers
- top_expenses
- expense_detail
- income_detail
- inventory
- forecast
- comparison

Rules:
- Do not write SQL.
- Do not return raw database rows.
- Focus on decision-making, not data listing.
- Use comparison for compare/vs/month-over-month questions.
- Use top_customers for customer concentration or revenue risk.
- Use forecast only when the user asks to forecast.
- Use period values compatible with this_month, last_month, this_year, last_year, today, yesterday.
"""


def _extract_json(text):
    match = re.search(r"\{.*\}", str(text or ""), re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def plan_executive_tools(question):
    try:
        response = ask_ai(f"{PLANNER_PROMPT}\n\nQuestion:\n{question}", timeout=60)
        data = _extract_json(response)
        plan = validate_plan((data or {}).get("tools"))
        if plan:
            return plan
    except Exception:
        pass
    return build_default_plan(question)


def _ai_summary(question, tool_results):
    compact = [
        {
            "tool": item.get("tool"),
            "args": item.get("args"),
            "result": item.get("result"),
        }
        for item in tool_results
    ]
    prompt = f"""
You are BigShot Intelligence, acting as CFO, senior business analyst, and strategic advisor for BigShot Company Limited.

Question:
{question}

Calculated data:
{json.dumps(compact, indent=2, default=str)}

Write one concise executive summary in senior consultant style.
Answer: so what does this mean for BigShot?
Do not output JSON.
Do not output database rows.
Do not invent facts outside the calculated data.
"""
    try:
        answer = ask_ai(prompt, timeout=90).strip()
        if answer:
            return answer
    except Exception:
        pass
    return None


def answer_executive_question(question):
    plan = plan_executive_tools(question)
    tool_results = execute_plan(plan)
    return format_executive_report(question, tool_results, ai_comment=_ai_summary(question, tool_results))
