BUSINESS_MENU = [
    ("sote_phwar", "Sote Phwar"),
    ("farm", "Farm"),
    ("factory", "Factory"),
    ("extension", "Extension"),
    ("inventory", "Inventory"),
    ("customers", "Customers"),
    ("financial_obligation", "Financial Obligation"),
]

BUSINESS_SECTOR = {
    "sote_phwar": "Sote Phwar",
    "farm": "Farm",
    "extension": "SP Extension",
    "factory": "SP Production",
}

MODULES = {
    "sote_phwar": [
        ("income", "Income"),
        ("expense", "Expense"),
        ("customers", "Customers"),
        ("kpi", "KPI"),
        ("cash_flow", "Cash Flow"),
    ],
    "farm": [
        ("income", "Income"),
        ("expense", "Expense"),
        ("crops_production", "Crops Production"),
        ("labor", "Labor"),
        ("kpi", "KPI"),
        ("cash_flow", "Cash Flow"),
    ],
    "factory": [
        ("factory_production", "Factory Production"),
        ("heho_west", "Heho Store (West)"),
        ("heho_home", "Heho Store (Home)"),
        ("tatkone_inventory", "Tatkone Inventory"),
        ("myit_thar_store", "Myit Thar Store"),
        ("min_hla_store", "Min Hla Store"),
        ("4l", "4L"),
        ("1l", "1L"),
        ("500ml", "500mL"),
        ("100ml", "100mL"),
        ("overview", "Overview"),
    ],
    "extension": [
        ("income", "Income"),
        ("expense", "Expense"),
        ("kpi", "KPI"),
        ("cash_flow", "Cash Flow"),
    ],
    "inventory": [
        ("inventory", "Inventory Analytics"),
    ],
    "customers": [
        ("customers", "Customer Analytics"),
    ],
    "financial_obligation": [
        ("financial_obligation", "Financial Obligation"),
    ],
}

INCOME_REPORTS = [
    ("total_income", "Total Income"),
    ("income_summary", "Income Summary"),
    ("sales_by_customer", "Sales by Customer"),
    ("sales_by_product", "Sales by Product"),
    ("top_customers", "Top Customers"),
    ("income_transactions", "Income Transactions"),
]

EXPENSE_REPORTS = [
    ("total_expense", "Total Expense"),
    ("expense_summary", "Expense Summary"),
    ("expense_by_category", "Expense by Category"),
    ("expense_detail", "Expense Detail"),
    ("top_expenses", "Top Expenses"),
]

CUSTOMER_REPORTS = [
    ("top_customers", "Top Customers"),
    ("customer_sales", "Customer Sales"),
    ("customer_history", "Customer History"),
    ("customer_profitability", "Customer Profitability"),
    ("outstanding_balance", "Outstanding Balance"),
]

INVENTORY_REPORTS = [
    ("current_stock", "Current Stock"),
    ("low_stock", "Low Stock"),
    ("inventory_movement", "Inventory Movement"),
    ("stock_valuation", "Stock Valuation"),
]

FINANCIAL_OBLIGATION_REPORTS = [
    ("financial_obligation_summary", "Obligation Summary"),
    ("financial_obligation_due", "Due Soon"),
    ("financial_obligation_list", "Obligation List"),
]

FACTORY_REPORTS = [
    ("factory_production", "Factory Production"),
    ("current_stock", "Current Stock"),
    ("inventory_movement", "Inventory Movement"),
    ("overview", "Overview"),
]

SIMPLE_REPORTS = {
    "kpi": [("kpi", "KPI")],
    "cash_flow": [("cash_flow", "Cash Flow")],
    "crops_production": [("crops_production", "Crops Production")],
    "labor": [("labor", "Labor")],
}

STORE_BY_MODULE = {
    "heho_west": "Heho Store (West)",
    "heho_home": "Heho Store (Home)",
    "tatkone_inventory": "Tatkone Inventory",
    "myit_thar_store": "Myint Thar Store",
    "min_hla_store": "Min Hla Store",
}

PRODUCT_BY_MODULE = {
    "4l": "Sote Phwar 4L",
    "1l": "Sote Phwar 1L",
    "500ml": "Sote Phwar 500 mL",
    "100ml": "Sote Phwar 100 mL",
}


def reports_for(business, module):
    if module == "income":
        return INCOME_REPORTS
    if module == "expense":
        return EXPENSE_REPORTS
    if module == "customers":
        return CUSTOMER_REPORTS
    if business == "customers":
        return CUSTOMER_REPORTS
    if business == "inventory" or module == "inventory":
        return INVENTORY_REPORTS
    if business == "financial_obligation" or module == "financial_obligation":
        return FINANCIAL_OBLIGATION_REPORTS
    if business == "factory":
        return FACTORY_REPORTS
    return SIMPLE_REPORTS.get(module, [(module, module.replace("_", " ").title())])


def report_needs_customer(report):
    return report in {"sales_by_customer", "customer_sales", "customer_history", "customer_profitability"}


def report_needs_category(report):
    return report in {"expense_by_category", "expense_detail"}
