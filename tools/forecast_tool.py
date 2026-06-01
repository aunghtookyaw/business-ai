from tools.nocodb_client import get_transactions

def forecast_business(question):

    records = get_transactions()

    total_income = 0
    total_expense = 0

    for r in records:

        amount = r.get("Amount", 0)

        if r.get("Income/Expense") == "Income":
            total_income += amount

        else:
            total_expense += amount

    net = total_income - total_expense

    if net > 0:
        return """
Forecast:
Business is likely stable next month
if current revenue trends continue.
"""

    return """
Forecast:
Business may face financial pressure
next month if expenses continue rising.
"""
