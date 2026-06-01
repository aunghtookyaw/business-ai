from tools.ai_kpi_engine import analyze_business
from tools.calculate_kpi import calculate_kpi
from tools.nocodb_client import get_transactions
from tools.forecast_tool import forecast_business
from tools.top_expenses import top_expenses
from tools.postgres_tool import query_database

TOOLS = {
    "analyze_business": analyze_business,
    "calculate_kpi": calculate_kpi,
    "get_transactions": get_transactions,
    "forecast_business": forecast_business,
    "top_expenses": top_expenses,
    "query_database": query_database,
}
