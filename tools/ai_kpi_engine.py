from tools.nocodb_client import get_transactions
from tools.openclaw_client import ask_ai


def calculate_sector_expense(records):

    sector_totals = {}

    for row in records:

        if row.get("Income/Expense") == "Expense":

            sector = row.get("Sector")
            amount = row.get("Amount", 0)

            if sector not in sector_totals:
                sector_totals[sector] = 0

            sector_totals[sector] += amount

    return sector_totals


def calculate_sector_income(records):

    sector_totals = {}

    for row in records:

        if row.get("Income/Expense") == "Income":

            sector = row.get("Sector")
            amount = row.get("Amount", 0)

            if sector not in sector_totals:
                sector_totals[sector] = 0

            sector_totals[sector] += amount

    return sector_totals


def analyze_business(question):

    records = get_transactions()

    income_data = calculate_sector_income(records)

    expense_data = calculate_sector_expense(records)

    summary = f"""
Sector Income:
{income_data}

Sector Expense:
{expense_data}
"""

    prompt = f"""
You are an expert agribusiness financial analyst.

Business:
- Vegetable Farming
- SP Extension
- SP Production
- Biofertilizer business

User Question:
{question}

Business KPI Summary:
{summary}

Analyze:
- profitability
- sector performance
- operational weakness
- forecasting
- recommendations
- risks

Reply professionally and concisely.
"""

    response = ask_ai(prompt)

    return response
