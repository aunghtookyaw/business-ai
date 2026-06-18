from datetime import datetime


def _money(value):
    try:
        return f"{int(value or 0):,} MMK"
    except (TypeError, ValueError):
        return str(value or "-")


def _number(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _metric_value(result, metric):
    if metric == "revenue":
        return _number(result.get("total_sales") or result.get("total_income") or result.get("income"))
    if metric == "expense":
        return _number(result.get("total_expense") or result.get("expense"))
    if metric == "profit":
        return _number(result.get("net_profit") or result.get("gross_profit"))
    return 0


def _tool_result(tool_results, tool_name):
    for item in tool_results:
        if item.get("tool") == tool_name:
            return item.get("result") or {}
    return {}


def _change_percent(current, previous):
    previous = _number(previous)
    if not previous:
        return None
    return round(((_number(current) - previous) / previous) * 100, 1)


def _trend_word(change_percent):
    if change_percent is None:
        return "No baseline"
    if change_percent > 5:
        return "Up"
    if change_percent < -5:
        return "Down"
    return "Stable"


def _summarize_tool(tool_result):
    tool = tool_result.get("tool")
    result = tool_result.get("result") or {}
    if tool == "kpi":
        return (
            f"Income {_money(result.get('total_income'))}, expense {_money(result.get('total_expense'))}, "
            f"net profit {_money(result.get('net_profit'))}."
        )
    if tool == "revenue":
        return f"Revenue is {_money(result.get('total_sales'))}; collected {_money(result.get('amount_received'))}; outstanding {_money(result.get('outstanding_amount'))}."
    if tool == "expense":
        return f"Expense is {_money(result.get('total_expense'))} across {result.get('expense_count', 0)} rows."
    if tool == "cash_flow":
        return f"Net cash flow is {_money(result.get('net_cash_flow'))}, with inflow {_money(result.get('total_inflow'))} and outflow {_money(result.get('total_outflow'))}."
    if tool == "top_customers":
        rows = result.get("income") or []
        if not rows:
            return "No customer revenue rows were found."
        top = rows[0]
        return f"Top revenue contributor is {top.get('customer_name') or top.get('item') or top.get('category') or '-'} at {_money(top.get('amount') or top.get('total_amount'))}."
    if tool == "top_expenses":
        rows = result.get("expenses") or []
        if not rows:
            return "No expense rows were found."
        top = rows[0]
        return f"Top expense is {top.get('item') or top.get('category') or '-'} at {_money(top.get('amount'))}."
    if tool in {"expense_detail", "income_detail"}:
        rows = result.get("transactions") or []
        total = sum(_number(row.get("amount")) for row in rows)
        return f"Found {len(rows)} transaction rows totaling {_money(total)}."
    if tool == "inventory":
        rows = result.get("stock") or result.get("movements") or []
        return f"Inventory tool returned {len(rows)} operational rows."
    if tool == "comparison":
        metric = result.get("metric") or "revenue"
        current = _metric_value(result.get("current") or {}, metric)
        previous = _metric_value(result.get("previous") or {}, metric)
        change = current - previous
        direction = "increased" if change > 0 else "decreased" if change < 0 else "stayed flat"
        return f"{metric.title()} {direction} by {_money(abs(change))}, from {_money(previous)} to {_money(current)}."
    if tool == "forecast":
        current = _metric_value(result.get("current") or {}, "revenue")
        previous = _metric_value(result.get("previous") or {}, "revenue")
        estimate = current + (current - previous)
        return f"Simple next-period revenue estimate is {_money(max(0, estimate))}, based on the latest period movement."
    return f"{tool} completed."


def _key_findings(tool_results):
    findings = [_summarize_tool(item) for item in tool_results]
    return findings or ["No business data was available for this question."]


def _analysis_lines(tool_results):
    lines = []
    for item in tool_results:
        tool = item.get("tool")
        result = item.get("result") or {}
        if tool == "comparison":
            metric = result.get("metric") or "revenue"
            current = _metric_value(result.get("current") or {}, metric)
            previous = _metric_value(result.get("previous") or {}, metric)
            if previous and current < previous:
                lines.append(f"{metric.title()} is below the previous period, so management should check whether this is seasonality, lost orders, or collection timing.")
            elif previous and current > previous:
                lines.append(f"{metric.title()} is ahead of the previous period. The next review should confirm whether growth came from repeatable customers or one-time transactions.")
        elif tool == "top_customers":
            rows = result.get("income") or []
            total = sum(_number(row.get("amount") or row.get("total_amount")) for row in rows)
            if rows and total:
                top = rows[0]
                top_amount = _number(top.get("amount") or top.get("total_amount"))
                share = round((top_amount / total) * 100, 1)
                lines.append(f"The largest listed customer contributes {share}% of the shown revenue, which is useful for growth but can create concentration risk.")
        elif tool == "top_expenses":
            rows = result.get("expenses") or []
            if rows:
                lines.append("Expense control should start with the highest-value rows because they have the largest immediate cash impact.")
        elif tool == "cash_flow":
            if _number(result.get("net_cash_flow")) < 0:
                lines.append("Cash flow is negative for the selected period, which can pressure purchasing and operating flexibility.")
    if not lines:
        lines.append("The available data gives a directional management view. Treat this as an operating signal and verify unusual movements against source transactions.")
    return lines


def _kpi_dashboard_lines(tool_results):
    kpi = _tool_result(tool_results, "kpi")
    revenue = _tool_result(tool_results, "revenue")
    expense = _tool_result(tool_results, "expense")
    cash = _tool_result(tool_results, "cash_flow")
    comparison = _tool_result(tool_results, "comparison")
    inventory = _tool_result(tool_results, "inventory")

    current_revenue = _number(kpi.get("total_income") or revenue.get("total_sales"))
    current_expense = _number(kpi.get("total_expense") or expense.get("total_expense"))
    current_profit = _number(kpi.get("net_profit") or kpi.get("gross_profit"))
    previous_revenue = _metric_value(comparison.get("previous") or {}, "revenue")
    previous_profit = _metric_value(comparison.get("previous") or {}, "profit")
    revenue_change = _change_percent(current_revenue, previous_revenue)
    profit_change = _change_percent(current_profit, previous_profit)
    stock_rows = inventory.get("stock") or []
    inventory_qty = sum(_number(row.get("stock_qty")) for row in stock_rows)
    rows = [
        ("Revenue", _money(current_revenue), _money(previous_revenue), revenue_change, _trend_word(revenue_change)),
        ("Expenses", _money(current_expense), "-", None, "Monitor"),
        ("Net Profit", _money(current_profit), _money(previous_profit), profit_change, _trend_word(profit_change)),
        ("Profit Margin %", f"{kpi.get('profit_margin_percent', 0)}%", "-", None, "Monitor"),
        ("Revenue Growth %", f"{revenue_change}%" if revenue_change is not None else "-", "-", None, _trend_word(revenue_change)),
        ("Profit Growth %", f"{profit_change}%" if profit_change is not None else "-", "-", None, _trend_word(profit_change)),
        ("Outstanding Receivables", _money(revenue.get("outstanding_amount")), "-", None, "Collection risk" if _number(revenue.get("outstanding_amount")) else "Stable"),
        ("Inventory Value", "0 MMK", "-", None, "Cost data needed" if stock_rows else "Not available"),
        ("Cash Position", _money(cash.get("net_cash_flow")), "-", None, "Cash pressure" if _number(cash.get("net_cash_flow")) < 0 else "Stable"),
        ("Loan Balance", "-", "-", None, "Not available"),
    ]
    return [
        "| KPI | Current | Previous | Change % | Trend |",
        "| --- | ------- | -------- | -------- | ----- |",
    ] + [
        f"| {name} | {current} | {previous} | {'-' if change is None else str(change) + '%'} | {trend} |"
        for name, current, previous, change, trend in rows
    ] + [
        f"Inventory quantity signal: {inventory_qty:,} units." if stock_rows else "Potential Data Quality Issue Detected: inventory value or quantity data is not available for this report."
    ]


def _risk_lines(tool_results):
    risks = []
    for item in tool_results:
        tool = item.get("tool")
        result = item.get("result") or {}
        if tool == "comparison":
            metric = result.get("metric") or "revenue"
            current = _metric_value(result.get("current") or {}, metric)
            previous = _metric_value(result.get("previous") or {}, metric)
            if previous:
                change_percent = round(((current - previous) / previous) * 100, 1)
                if abs(change_percent) > 10:
                    risks.append(f"{metric.title()} changed by {change_percent}%, above the 10% management review threshold.")
        if tool == "revenue" and _number(result.get("outstanding_amount")) > 0:
            risks.append(f"Outstanding receivables total {_money(result.get('outstanding_amount'))}; collection discipline should be monitored.")
        if tool == "cash_flow" and _number(result.get("net_cash_flow")) < 0:
            risks.append("Negative net cash flow may restrict operating flexibility if it continues.")
        if tool == "inventory":
            rows = result.get("stock") or []
            if any(_number(row.get("stock_qty")) <= 0 for row in rows):
                risks.append("Potential Data Quality Issue Detected: some inventory rows show zero or negative stock and should be verified.")
    return risks or ["No critical risk threshold was triggered by the available data."]


def _opportunity_lines(tool_results):
    tools = {item.get("tool") for item in tool_results}
    opportunities = []
    if "top_customers" in tools:
        opportunities.append("Use the strongest revenue customers as a base for repeat orders, upsell, and referral growth.")
    if "top_expenses" in tools or "expense" in tools:
        opportunities.append("Target high-value recurring cost categories for budget control and procurement review.")
    if "cash_flow" in tools:
        opportunities.append("Improve cash conversion by prioritizing collection timing and payment-method visibility.")
    if "inventory" in tools:
        opportunities.append("Improve inventory turnover by linking stock movement to customer demand and product margins.")
    return opportunities or ["The main opportunity is to convert this analysis into one measurable management action for the next period."]


def _recommendations(tool_results):
    tools = {item.get("tool") for item in tool_results}
    recommendations = []
    if "top_customers" in tools:
        recommendations.append("Monitor customer concentration and build secondary revenue sources where one customer dominates sales.")
    if "top_expenses" in tools or "expense" in tools or "expense_detail" in tools:
        recommendations.append("Review the largest expense categories first and set approval thresholds for repeated spending.")
    if "cash_flow" in tools:
        recommendations.append("Separate collection timing from profitability and follow up on delayed inflows before adding new cash commitments.")
    if "inventory" in tools:
        recommendations.append("Connect inventory movement with sales and cost data so turnover and valuation can be managed at CEO level.")
    if not recommendations:
        recommendations.append("Review the underlying transactions for outliers, then set one measurable action for the next reporting period.")
    return recommendations


def _forecast_lines(tool_results):
    for item in tool_results:
        if item.get("tool") == "forecast":
            result = item.get("result") or {}
            current = _metric_value(result.get("current") or {}, "revenue")
            previous = _metric_value(result.get("previous") or {}, "revenue")
            estimate = max(0, current + (current - previous))
            return [f"Estimated future revenue: {_money(estimate)}. This is an estimate based only on recent movement, not a guaranteed forecast."]
    return []


def _business_meaning_line(tool_results):
    risks = _risk_lines(tool_results)
    opportunities = _opportunity_lines(tool_results)
    risk = risks[0] if risks else "No critical risk threshold was triggered by the available data."
    opportunity = opportunities[0] if opportunities else "Convert this analysis into one measurable management action."
    return f"What this means for BigShot: {risk} {opportunity}"


def _top_rows(result, key, amount_keys=("amount", "total_amount")):
    rows = result.get(key) or []
    output = []
    total = sum(_number(row.get(amount_keys[0]) or row.get(amount_keys[-1])) for row in rows) or 1
    for row in rows[:5]:
        amount = _number(row.get(amount_keys[0]) or row.get(amount_keys[-1]))
        label = row.get("customer_name") or row.get("item") or row.get("category") or row.get("product") or "-"
        output.append(f"- {label}: {_money(amount)} ({round((amount / total) * 100, 1)}% of shown total)")
    return output


def _revenue_analysis_lines(tool_results):
    revenue = _tool_result(tool_results, "revenue")
    top_customers = _tool_result(tool_results, "top_customers")
    comparison = _tool_result(tool_results, "comparison")
    lines = [
        f"Revenue: {_money(revenue.get('total_sales') or revenue.get('total_income'))}; collected {_money(revenue.get('amount_received'))}; outstanding {_money(revenue.get('outstanding_amount'))}.",
    ]
    if comparison:
        current = _metric_value(comparison.get("current") or {}, "revenue")
        previous = _metric_value(comparison.get("previous") or {}, "revenue")
        change = _change_percent(current, previous)
        lines.append(f"Revenue comparison: current {_money(current)} vs previous {_money(previous)}; growth {'-' if change is None else str(change) + '%'}; trend {_trend_word(change)}.")
    rows = _top_rows(top_customers, "income")
    lines.extend(rows or ["- No top customer or product contribution data was available."])
    lines.append("Key revenue driver interpretation: prioritize contributors with the highest share and check whether growth is repeatable or one-time.")
    return lines


def _expense_analysis_lines(tool_results):
    expense = _tool_result(tool_results, "expense")
    top_expense_rows = _top_rows(_tool_result(tool_results, "top_expenses"), "expenses")
    lines = [f"Expenses: {_money(expense.get('total_expense'))} across {expense.get('expense_count', 0)} rows."]
    lines.extend(top_expense_rows or ["- No top expense category data was available."])
    lines.append("Cost-driver interpretation: management attention should start with the largest categories and any category that increased above 10%.")
    lines.append("Potential Data Quality Issue Detected: categories falling to zero or missing categories require source review when they conflict with normal operations.")
    return lines


def _profitability_lines(tool_results):
    kpi = _tool_result(tool_results, "kpi")
    revenue = _number(kpi.get("total_income"))
    expense = _number(kpi.get("total_expense"))
    profit = _number(kpi.get("net_profit") or kpi.get("gross_profit"))
    margin = kpi.get("profit_margin_percent", 0)
    sustainability = "sustainable" if profit > 0 and float(margin or 0) > 10 else "under pressure"
    return [
        f"Revenue {_money(revenue)}, expenses {_money(expense)}, net profit {_money(profit)}, profit margin {margin}%.",
        f"Profitability is {sustainability}; management should protect margin before pursuing revenue growth that requires heavy spending.",
    ]


def _customer_analysis_lines(tool_results):
    revenue = _tool_result(tool_results, "revenue")
    top_customers = _tool_result(tool_results, "top_customers")
    lines = _top_rows(top_customers, "income") or ["- No customer concentration data was available."]
    outstanding = _number(revenue.get("outstanding_amount"))
    if outstanding:
        lines.append(f"Collection risk: outstanding receivables are {_money(outstanding)} and should be followed up by customer priority.")
    return lines


def _inventory_analysis_lines(tool_results):
    inventory = _tool_result(tool_results, "inventory")
    stock = inventory.get("stock") or []
    if not stock:
        return ["Potential Data Quality Issue Detected: inventory rows were not available for this business unit or period."]
    lines = ["| Product | Region | Quantity | Reorder Level | Status |", "| ------- | ------ | -------- | ------------- | ------ |"]
    for row in stock[:10]:
        qty = _number(row.get("stock_qty"))
        status = "Low stock" if qty <= 10 else "Available"
        lines.append(f"| {row.get('product') or '-'} | {row.get('store') or row.get('region') or '-'} | {qty:,} | 10 | {status} |")
    return lines


def _growth_analysis_lines(tool_results):
    comparison = _tool_result(tool_results, "comparison")
    if not comparison:
        return ["Growth comparison data was not available. Use the selected period against the previous period to calculate growth."]
    metric = comparison.get("metric") or "revenue"
    current = _metric_value(comparison.get("current") or {}, metric)
    previous = _metric_value(comparison.get("previous") or {}, metric)
    growth = _change_percent(current, previous)
    status = "Growing" if growth is not None and growth > 5 else "Contracting" if growth is not None and growth < -5 else "Stable"
    return [
        f"{metric.title()} growth rate = (current {_money(current)} - previous {_money(previous)}) / previous x 100 = {'-' if growth is None else str(growth) + '%'}.",
        f"Growth classification: {status}.",
    ]


def _management_conclusion_lines(tool_results):
    risks = _risk_lines(tool_results)
    recommendations = _recommendations(tool_results)
    risk_text = risks[0] if risks else "No critical risk threshold was triggered."
    return [
        f"Business strength: {risk_text}",
        "Top 3 management priorities: cash discipline, profit margin protection, and revenue quality.",
        f"CEO focus next: {recommendations[0] if recommendations else 'Set one measurable KPI action for the next period.'}",
        "What does this mean for BigShot and what should management do next? Management should focus first on cash and profit protection, then scale the revenue drivers that are supported by repeatable customer demand.",
    ]


def format_executive_report(question, tool_results, ai_comment=None):
    findings = _key_findings(tool_results)
    lines = [
        "BigShot Intelligence Report",
        f"Question: {question}",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "Executive Summary",
        ai_comment or findings[0],
        _business_meaning_line(tool_results),
        "",
        "KPI Dashboard",
    ]
    lines.extend(_kpi_dashboard_lines(tool_results))
    lines.extend(["", "Key Findings"])
    lines.extend(f"- {finding}" for finding in findings[:6])
    lines.extend(["", "Revenue Analysis"])
    lines.extend(_revenue_analysis_lines(tool_results))
    lines.extend(["", "Expense Analysis"])
    lines.extend(_expense_analysis_lines(tool_results))
    lines.extend(["", "Profitability Analysis"])
    lines.extend(f"- {line}" for line in _profitability_lines(tool_results))
    lines.extend(["", "Customer Analysis"])
    lines.extend(_customer_analysis_lines(tool_results))
    lines.extend(["", "Inventory Analysis"])
    lines.extend(_inventory_analysis_lines(tool_results))
    lines.extend(["", "Business Growth Analysis"])
    lines.extend(f"- {line}" for line in _growth_analysis_lines(tool_results))
    lines.extend(["", "Trend Analysis"])
    lines.extend(f"- {line}" for line in _analysis_lines(tool_results))
    lines.extend(["", "Risk Analysis / Risks & Concerns"])
    lines.extend(f"- {line}" for line in _risk_lines(tool_results))
    lines.extend(["", "Opportunities"])
    lines.extend(f"- {line}" for line in _opportunity_lines(tool_results))
    lines.extend(["", "Recommendations"])
    recommendations = _recommendations(tool_results)
    action_labels = ["Immediate Actions", "Short-Term Actions", "Strategic Actions"]
    for index, label in enumerate(action_labels):
        action = recommendations[index] if index < len(recommendations) else recommendations[-1]
        lines.append(f"- {label}: {action}")
    forecast = _forecast_lines(tool_results)
    if forecast:
        lines.extend(["", "Forecast"])
        lines.extend(f"- {line}" for line in forecast)
    lines.extend(["", "Management Conclusion"])
    lines.extend(f"- {line}" for line in _management_conclusion_lines(tool_results))
    lines.extend(["", "Supporting Data"])
    lines.extend(f"- {finding}" for finding in findings[:4])
    return "\n".join(lines)


def write_executive_excel_report(report_text, output_path):
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Executive Report"
    for row_index, line in enumerate(str(report_text or "").splitlines(), start=1):
        sheet.cell(row=row_index, column=1, value=line)
    workbook.save(output_path)
