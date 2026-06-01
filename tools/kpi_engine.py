from tools.nocodb_client import get_transactions

def calculate_kpi(dummy=""):

    records = get_transactions()

    total_income = 0
    total_expense = 0

    for r in records:

        amount = r.get("Amount", 0)

        if r.get("Income/Expense") == "Income":
            total_income += amount

        else:
            total_expense += amount

    net_profit = total_income - total_expense

    return f"""
Total Income: {total_income}

Total Expense: {total_expense}

Net Profit: {net_profit}
"""
