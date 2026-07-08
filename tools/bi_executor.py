from tools.bi_catalog import BUSINESS_SECTOR, PRODUCT_BY_MODULE, STORE_BY_MODULE
from tools.bi_intents import validate_intent
from tools.bi_periods import legacy_period, period_label
from tools.formula_engine import (
    business_cash_flow,
    business_kpi_overview,
    calculate_inventory_value,
    cash_flow,
    category_summary,
    expense_total,
    farm_product_ranking,
    farm_transection_customer,
    financial_obligation_due,
    financial_obligation_list,
    financial_obligation_summary,
    get_income_detail,
    gross_profit,
    kpi_overview,
    list_transactions,
    sales_total,
    sotephwar_inventory_list,
    sotephwar_inventory_movement_summary,
    sotephwar_inventory_stock,
    sotephwar_product_ranking,
    sotephwar_transection_customer,
    sotephwar_transection_list,
    sotephwar_transection_quantity,
    sotephwar_transection_summary,
    sotephwar_transection_top,
    top_expenses,
    top_income,
)


def _filters(intent, income_expense=None):
    filters = {}
    sector = BUSINESS_SECTOR.get(intent.business)
    if sector:
        filters["sector"] = sector
    if income_expense:
        filters["income_expense"] = income_expense
    if intent.categories:
        filters["categories"] = intent.categories
    if intent.category:
        filters["category"] = intent.category
    return filters


def _farm_customer_filters(intent, income_expense="Income"):
    filters = _filters(intent, income_expense)
    if intent.customer:
        filters["farm_customer"] = intent.customer
    return filters


def _store(intent):
    return intent.store or STORE_BY_MODULE.get(intent.module)


def _product(intent):
    return intent.product or PRODUCT_BY_MODULE.get(intent.module)


def _voucher_limit(intent):
    return 200 if intent.output == "pdf" else 50


def execute_intent(intent):
    missing = validate_intent(intent)
    if missing:
        raise ValueError("Incomplete BI intent: " + ", ".join(missing))

    period = legacy_period(intent.period)
    report = intent.report

    if intent.business == "sote_phwar" and report == "total_income":
        result = sales_total(period, _filters(intent, "Income"))
    elif intent.business == "sote_phwar" and report == "income_summary":
        result = top_income(period, _filters(intent, "Income"), limit=50)
    elif intent.business == "sote_phwar" and report == "income_by_category":
        result = category_summary(period, _filters(intent, "Income"))
    elif intent.business == "farm" and report == "total_income":
        result = sales_total(period, _filters(intent, "Income"))
    elif intent.business == "farm" and report == "income_summary":
        result = top_income(period, _filters(intent, "Income"), limit=50)
    elif intent.business == "farm" and report == "income_by_category":
        result = category_summary(period, _filters(intent, "Income"))
    elif intent.business == "farm" and report in {"sales_by_product", "top_products"}:
        result = farm_product_ranking(period, product=_product(intent), limit=50)
    elif report == "financial_obligation_summary":
        result = financial_obligation_summary()
    elif report == "financial_obligation_due":
        result = financial_obligation_due(days=30, status="Active", limit=50)
    elif report == "financial_obligation_list":
        result = financial_obligation_list(limit=50)
    elif report == "total_income":
        result = sales_total(period, _filters(intent, "Income"))
    elif report == "income_summary":
        result = top_income(period, _filters(intent, "Income"), limit=50)
    elif report == "income_by_category":
        result = category_summary(period, _filters(intent, "Income"))
    elif intent.business == "farm" and report == "sales_by_customer":
        result = farm_transection_customer(period, customer=intent.customer, limit=_voucher_limit(intent))
    elif report == "sales_by_customer":
        result = sotephwar_transection_customer(period, customer=intent.customer, limit=_voucher_limit(intent))
    elif report == "top_customers":
        result = top_income(period, _filters(intent, "Income"), limit=10)
    elif intent.business == "sote_phwar" and report == "top_products":
        result = sotephwar_product_ranking(period, product=_product(intent), limit=10)
    elif intent.business == "farm" and report == "top_products":
        result = farm_product_ranking(period, product=_product(intent), limit=10)
    elif report == "sales_by_product":
        result = sotephwar_transection_quantity(period, item=_product(intent))
    elif intent.business in {"farm", "sote_phwar"} and report in {"income_detail", "income_transactions"}:
        result = get_income_detail(
            BUSINESS_SECTOR[intent.business],
            period,
            customer=intent.customer,
            category=intent.category,
            categories=intent.categories,
            limit=200 if intent.output == "pdf" else 50,
        )
    elif report in {"income_detail", "income_transactions"}:
        result = list_transactions(period, _filters(intent, "Income"), limit=50)
    elif report == "total_expense":
        result = expense_total(period, _filters(intent, "Expense"))
    elif report in {"expense_summary", "expense_by_category"}:
        result = category_summary(period, _filters(intent, "Expense"))
    elif report == "expense_detail":
        result = list_transactions(period, _filters(intent, "Expense"), limit=50)
    elif report == "top_expenses":
        result = top_expenses(period, _filters(intent, "Expense"), limit=10)
    elif report == "customer_history":
        result = sotephwar_transection_customer(period, customer=intent.customer, limit=_voucher_limit(intent))
    elif report == "customer_sales":
        result = sotephwar_transection_customer(period, customer=intent.customer, limit=_voucher_limit(intent))
    elif report == "customer_profitability":
        result = sotephwar_transection_customer(period, customer=intent.customer, limit=_voucher_limit(intent))
        result["note"] = "Profitability uses voucher totals and outstanding balance; direct cost by customer is not available yet."
    elif intent.business == "farm" and report == "outstanding_balance":
        result = farm_transection_customer(period, customer=intent.customer, limit=200, unpaid_only=True)
    elif report == "outstanding_balance":
        result = sotephwar_transection_customer(period, customer=intent.customer, limit=_voucher_limit(intent), unpaid_only=True)
    elif report == "stock_valuation":
        result = calculate_inventory_value(product=_product(intent), store=_store(intent))
    elif report in {"current_stock", "low_stock"}:
        result = sotephwar_inventory_stock(product=_product(intent), store=_store(intent))
        if report == "low_stock":
            result["stock"] = [row for row in result["stock"] if row.get("stock_qty", 0) <= 10]
            result["note"] = "Low stock threshold: 10 units."
    elif report in {"inventory_movement", "factory_production", "crops_production"}:
        movement_type = "Production" if report in {"factory_production", "crops_production"} else None
        result = sotephwar_inventory_movement_summary(
            period,
            product=_product(intent),
            store=_store(intent),
            movement_type=movement_type,
        )
    elif intent.business in {"farm", "sote_phwar"} and report == "kpi":
        result = business_kpi_overview(period, business=intent.business, filters=_filters(intent))
    elif intent.business in {"farm", "sote_phwar"} and report == "cash_flow":
        result = business_cash_flow(period, business=intent.business, filters=_filters(intent))
    elif intent.business in {"farm", "sote_phwar"} and report == "overview":
        result = gross_profit(period, _filters(intent))
    elif report == "kpi":
        result = kpi_overview(period, _filters(intent))
    elif report == "cash_flow":
        result = cash_flow(period, _filters(intent))
    elif report == "labor":
        intent.category = intent.category or "Bonus for Labour"
        result = list_transactions(period, _filters(intent, "Expense"), limit=50)
    elif report == "overview":
        result = gross_profit(period, _filters(intent))
    else:
        result = list_transactions(period, _filters(intent), limit=50)

    title = _title(intent)
    label = period_label(intent.period)
    if isinstance(result, dict):
        result["_bi_intent"] = intent.to_dict()
        result["_report_title"] = title
        result["_period_label"] = label

    return {
        "intent": intent.to_dict(),
        "title": title,
        "period_label": label,
        "result": result,
    }


def _title(intent):
    parts = [
        intent.business.replace("_", " ").title(),
        intent.module.replace("_", " ").title(),
        intent.report.replace("_", " ").title(),
    ]
    if intent.customer:
        parts.append(intent.customer)
    if intent.category:
        parts.append(intent.category)
    if intent.categories:
        parts.append(", ".join(intent.categories))
    return " - ".join(parts)
