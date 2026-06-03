from tools.nocodb_client import get_transactions


def _amount(value):
    if value in (None, ""):
        return 0
    return float(value)


def top_expenses(limit_text):

    records = get_transactions()

    expenses = []

    for r in records:

        if r.get("Income/Expense") == "Expense":

            expenses.append({
                "date": r.get("Date"),
                "item": r.get("Item/Description"),
                "category": r.get("Categorization"),
                "sector": r.get("Sector"),
                "payment_method": r.get("Payment Method"),
                "amount": _amount(r.get("Amount")),
            })

    expenses.sort(
        key=lambda x: x["amount"],
        reverse=True
    )

    limit = int(limit_text)

    result = ""

    for e in expenses[:limit]:

        result += (
            f"{e['amount']:,.0f} - {e['item']} "
            f"({e['sector']} / {e['category']}, {e['payment_method']})\n"
        )

    return result
