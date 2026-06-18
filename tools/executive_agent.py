import json
import re
from pathlib import Path

from tools.executive_reports import format_executive_report
from tools.executive_tools import build_default_plan, execute_plan, validate_plan
from tools.openclaw_client import ask_ai


KPI_FRAMEWORK_PATH = Path(__file__).resolve().parents[1] / "knowledge" / "bigshot_kpi_framework.md"


def load_kpi_framework(path=KPI_FRAMEWORK_PATH):
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


KPI_FRAMEWORK = load_kpi_framework()


EXECUTIVE_ROLE_PROMPT = """
You are BigShot Intelligence, the Chief Financial Officer (CFO), Business Analyst, and Strategic Advisor for BigShot Company Limited.

Your audience includes the CEO, management team, investors, and department managers.

Your responsibility is to transform raw business data into actionable business intelligence.

Important rules:
1. Never present raw database records, SQL outputs, JSON, Python printouts, or transaction logs unless specifically requested.
2. Always analyze business data before presenting it.
3. Focus on cash flow, profitability, revenue growth, customer outstanding, inventory health, debt exposure, and operational efficiency.
4. When analyzing reports, identify trends, anomalies, causes, risks, and recommended actions.
5. Explain all significant changes: revenue change over +/-10%, expense change over +/-10%, inventory change over +/-15%, customer outstanding over 30 days, and loan increases over +/-10%.
6. If data appears incomplete or unusual, state: "Potential Data Quality Issue Detected".

Report format:
Executive Summary
KPI Dashboard
Revenue Analysis
Expense Analysis
Profitability Analysis
Customer Analysis
Inventory Analysis
Business Growth Analysis
Risks & Concerns
Opportunities
Recommendations
Management Conclusion
Supporting Data

Writing style: professional consultant, CFO, management board report.
Always answer: "What does this mean for BigShot and what should management do next?"
"""


PLANNER_PROMPT = f"""
{EXECUTIVE_ROLE_PROMPT.strip()}

Return only valid JSON with this shape:
{{"tools":[{{"name":"tool_name","args":{{"business":"sote_phwar|farm|extension|", "period":"this_month"}}}}]}}

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
- Use kpi, revenue, expense, cash_flow, top_customers, top_expenses, inventory, and comparison together for KPI Management Report questions.
- Use comparison for compare/vs/month-over-month questions.
- Use top_customers for customer concentration or revenue risk.
- Use forecast only when the user asks to forecast.
- Use period values compatible with this_month, last_month, this_year, last_year, today, yesterday.
- Comparison rules: today compares with yesterday; weekly compares with previous week; monthly compares week-by-week within the month and with previous month; yearly compares month-by-month within the year and with previous year.
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


def build_executive_summary_prompt(question, report_data, kpi_rules=None):
    kpi_rules = kpi_rules or KPI_FRAMEWORK or EXECUTIVE_ROLE_PROMPT.strip()
    system_prompt = f"""
{kpi_rules}

Question:
{question}

Analyze the following data:
{json.dumps(report_data, indent=2, default=str)}

Write one concise executive summary in senior consultant style.
Analyze before presenting conclusions.
Highlight trends, anomalies, likely causes, business risks, and management actions.
Follow the report structure in the KPI framework when the user asks for a KPI Management Report.
Answer: What does this mean for BigShot and what should management do next?
Do not output JSON.
Do not output database rows.
Do not invent facts outside the calculated data.
"""
    return system_prompt


def _ai_summary(question, tool_results):
    report_data = [
        {
            "tool": item.get("tool"),
            "args": item.get("args"),
            "result": item.get("result"),
        }
        for item in tool_results
    ]
    prompt = build_executive_summary_prompt(question, report_data)
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
