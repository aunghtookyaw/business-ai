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
    metrics = []
    for item in tool_results:
        tool = item.get("tool")
        result = item.get("result") or {}
        if tool == "kpi":
            metrics.extend([
                f"Revenue: {_money(result.get('total_income'))}",
                f"Expense: {_money(result.get('total_expense'))}",
                f"Net Profit: {_money(result.get('net_profit'))}",
                f"Profit Margin: {result.get('profit_margin_percent', 0)}%",
            ])
        elif tool == "revenue":
            metrics.extend([
                f"Revenue: {_money(result.get('total_sales'))}",
                f"Collected: {_money(result.get('amount_received'))}",
                f"Outstanding: {_money(result.get('outstanding_amount'))}",
            ])
        elif tool == "expense":
            metrics.append(f"Expense: {_money(result.get('total_expense'))}")
        elif tool == "cash_flow":
            metrics.extend([
                f"Cash Inflow: {_money(result.get('total_inflow'))}",
                f"Cash Outflow: {_money(result.get('total_outflow'))}",
                f"Net Cash Flow: {_money(result.get('net_cash_flow'))}",
            ])
    return metrics or ["No KPI metrics were available from the selected tools."]


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


def format_executive_report(question, tool_results, ai_comment=None):
    findings = _key_findings(tool_results)
    lines = [
        "BigShot Intelligence Report",
        f"Question: {question}",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "Executive Summary",
        ai_comment or findings[0],
        "",
        "KPI Dashboard",
    ]
    lines.extend(f"- {metric}" for metric in _kpi_dashboard_lines(tool_results))
    lines.extend(["", "Key Findings"])
    lines.extend(f"- {finding}" for finding in findings[:6])
    lines.extend(["", "Trend Analysis"])
    lines.extend(f"- {line}" for line in _analysis_lines(tool_results))
    lines.extend(["", "Risks & Concerns"])
    lines.extend(f"- {line}" for line in _risk_lines(tool_results))
    lines.extend(["", "Opportunities"])
    lines.extend(f"- {line}" for line in _opportunity_lines(tool_results))
    lines.extend(["", "Recommendations"])
    lines.extend(f"- {line}" for line in _recommendations(tool_results))
    forecast = _forecast_lines(tool_results)
    if forecast:
        lines.extend(["", "Forecast"])
        lines.extend(f"- {line}" for line in forecast)
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
