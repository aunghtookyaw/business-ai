from tools.query_database import query_database


def calculate_kpi(*args):

    income_query = '''
    SELECT SUM("Amount")
    FROM "pipkgfu2wr9qxyy"."Transection"
    WHERE "Income_Expense" = 'Income'
    '''

    expense_query = '''
    SELECT SUM("Amount")
    FROM "pipkgfu2wr9qxyy"."Transection"
    WHERE "Income_Expense" = 'Expense'
    '''

    income_result = query_database(income_query)
    expense_result = query_database(expense_query)

    total_income = income_result[0]["sum"] if income_result else 0
    total_expense = expense_result[0]["sum"] if expense_result else 0

    try:
        profit = float(total_income) - float(total_expense)
    except:
        profit = 0

    return {
        "total_income": total_income,
        "total_expense": total_expense,
        "profit": profit
    }
