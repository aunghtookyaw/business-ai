from tools.nocodb_client import get_transactions

def top_expenses(limit_text):

    records = get_transactions()

    expenses = []

    for r in records:

        if r.get("Income/Expense") == "Expense":

            expenses.append({
                "item": r.get("Item/Description"),
                "amount": r.get("Amount", 0)
            })

    expenses.sort(
        key=lambda x: x["amount"],
        reverse=True
    )

    limit = int(limit_text)

    result = ""

    for e in expenses[:limit]:

        result += (
            f"{e['item']} "
            f"- {e['amount']}\n"
        )

    return result
