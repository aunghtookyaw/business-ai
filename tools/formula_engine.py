from datetime import date, datetime, time, timedelta
import re
from time import monotonic

import psycopg2
import psycopg2.extras

import config


MONTH_ALIASES = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "mrch": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}

SECTOR_ALIASES = {
    "farm": "Farm",
    "sp extension": "SP Extension",
    "extension": "SP Extension",
    "sp production": "SP Production",
    "production": "SP Production",
    "sotephwar": "SP Production",
    "sote phwar": "SP Production",
}

CATEGORY_ALIASES = {
    "agrochemical": "Agrochemicals",
    "agrochemicals": "Agrochemicals",
    "bonus labour": "Bonus for Labour",
    "bonus for labour": "Bonus for Labour",
    "machinary": "Machinary Equipment ",
    "machinery": "Machinary Equipment ",
    "equipment": "Machinary Equipment ",
    "machinary equipment": "Machinary Equipment ",
    "machinery equipment": "Machinary Equipment ",
}

DIMENSION_VALUES_TTL_SECONDS = 300
DIMENSION_COLUMNS = {
    "income_expense": "Income_Expense",
    "sector": "Sector",
    "category": "Categorization",
    "item_description": "Item_Description",
    "payment_method": "Payment_Method",
}
_DIMENSION_VALUES_CACHE = {
    "expires_at": 0,
    "values": None,
}


def _table_ref():
    schema = config.TRANSACTION_SCHEMA.replace('"', '""')
    table = config.TRANSACTION_TABLE.replace('"', '""')
    return f'"{schema}"."{table}"'


def _connect():
    return psycopg2.connect(
        host=config.POSTGRES_HOST,
        database=config.POSTGRES_DB,
        user=config.POSTGRES_USER,
        password=config.POSTGRES_PASSWORD,
        port=config.POSTGRES_PORT,
    )


def _fetch_all(sql, params=None):
    with _connect() as connection:
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(sql, params or {})
            return [dict(row) for row in cursor.fetchall()]


def _fetch_one(sql, params=None):
    rows = _fetch_all(sql, params)
    return rows[0] if rows else {}


def _period_dates(period):
    today = date.today()

    month_match = re.fullmatch(r"month:(\d{4})-(\d{2})", period)
    year_match = re.fullmatch(r"year:(\d{4})", period)

    if month_match:
        year = int(month_match.group(1))
        month = int(month_match.group(2))
        start_date = date(year, month, 1)
        if month == 12:
            end_date = date(year + 1, 1, 1)
        else:
            end_date = date(year, month + 1, 1)
    elif year_match:
        year = int(year_match.group(1))
        start_date = date(year, 1, 1)
        end_date = date(year + 1, 1, 1)
    elif period == "yesterday":
        start_date = today - timedelta(days=1)
        end_date = today
    elif period == "today":
        start_date = today
        end_date = today + timedelta(days=1)
    elif period == "this_week":
        days_since_sunday = (today.weekday() + 1) % 7
        start_date = today - timedelta(days=days_since_sunday)
        end_date = start_date + timedelta(days=7)
    elif period == "last_week":
        days_since_sunday = (today.weekday() + 1) % 7
        end_date = today - timedelta(days=days_since_sunday)
        start_date = end_date - timedelta(days=7)
    elif period == "this_month":
        start_date = today.replace(day=1)
        if start_date.month == 12:
            end_date = start_date.replace(year=start_date.year + 1, month=1)
        else:
            end_date = start_date.replace(month=start_date.month + 1)
    elif period == "last_month":
        first_day_this_month = today.replace(day=1)
        end_date = first_day_this_month
        if first_day_this_month.month == 1:
            start_date = first_day_this_month.replace(
                year=first_day_this_month.year - 1,
                month=12,
            )
        else:
            start_date = first_day_this_month.replace(
                month=first_day_this_month.month - 1,
            )
    elif period == "this_year":
        start_date = today.replace(month=1, day=1)
        end_date = start_date.replace(year=start_date.year + 1)
    elif period == "last_year":
        end_date = today.replace(month=1, day=1)
        start_date = end_date.replace(year=end_date.year - 1)
    else:
        return None, None

    offset = timedelta(minutes=config.LOCAL_UTC_OFFSET_MINUTES)
    start = datetime.combine(start_date, time.min) - offset
    end = datetime.combine(end_date, time.min) - offset

    return start, end


def _date_filter(period):
    start, end = _period_dates(period)
    if start is None:
        return "", {}

    return 'AND "Date" >= %(start)s AND "Date" < %(end)s', {
        "start": start,
        "end": end,
    }


def _normalized_text(text):
    return " ".join(re.sub(r"[^a-z0-9\s]", " ", text.lower()).split())


def _contains_phrase(text, phrase):
    return re.search(rf"(^|\s){re.escape(phrase)}($|\s)", text) is not None


def clear_dimension_value_cache():
    _DIMENSION_VALUES_CACHE["expires_at"] = 0
    _DIMENSION_VALUES_CACHE["values"] = None


def _load_dimension_values():
    row = _fetch_one(
        f'''
        SELECT
          ARRAY_REMOVE(ARRAY_AGG(DISTINCT NULLIF(TRIM("Income_Expense"), '')), NULL) AS income_expenses,
          ARRAY_REMOVE(ARRAY_AGG(DISTINCT NULLIF(TRIM("Sector"), '')), NULL) AS sectors,
          ARRAY_REMOVE(ARRAY_AGG(DISTINCT NULLIF(TRIM("Categorization"), '')), NULL) AS categories,
          ARRAY_REMOVE(ARRAY_AGG(DISTINCT NULLIF(TRIM("Item_Description"), '')), NULL) AS item_descriptions,
          ARRAY_REMOVE(ARRAY_AGG(DISTINCT NULLIF(TRIM("Payment_Method"), '')), NULL) AS payment_methods
        FROM {_table_ref()}
        WHERE COALESCE(__nc_deleted, false) = false
        '''
    )
    return {
        "income_expenses": sorted(row.get("income_expenses") or []),
        "sectors": sorted(row.get("sectors") or []),
        "categories": sorted(row.get("categories") or []),
        "item_descriptions": sorted(row.get("item_descriptions") or []),
        "payment_methods": sorted(row.get("payment_methods") or []),
    }


def _dimension_values():
    now = monotonic()
    if (
        _DIMENSION_VALUES_CACHE["values"] is None
        or _DIMENSION_VALUES_CACHE["expires_at"] <= now
    ):
        _DIMENSION_VALUES_CACHE["values"] = _load_dimension_values()
        _DIMENSION_VALUES_CACHE["expires_at"] = now + DIMENSION_VALUES_TTL_SECONDS

    return _DIMENSION_VALUES_CACHE["values"]


def _known_dimension_values():
    try:
        return _dimension_values()
    except Exception:
        return {
            "income_expenses": [],
            "sectors": [],
            "categories": [],
            "item_descriptions": [],
            "payment_methods": [],
        }


def _find_known_value(text, values):
    for value in values:
        normalized_value = _normalized_text(value).strip()
        if normalized_value and _contains_phrase(text, normalized_value):
            return value

    return None


def extract_dimension_filters(question):
    text = _normalized_text(question)
    filters = {}

    for alias, sector in SECTOR_ALIASES.items():
        if _contains_phrase(text, alias):
            filters["sector"] = sector
            break

    for alias, category in CATEGORY_ALIASES.items():
        if _contains_phrase(text, alias):
            filters["category"] = category
            break

    known_values = _known_dimension_values()

    if "sector" not in filters:
        sector = _find_known_value(text, known_values["sectors"])
        if sector:
            filters["sector"] = sector

    if "category" not in filters:
        category = _find_known_value(text, known_values["categories"])
        if category:
            filters["category"] = category

    if "item_description" not in filters:
        item_description = _find_known_value(text, known_values["item_descriptions"])
        if item_description:
            filters["item_description"] = item_description

    if "payment_method" not in filters:
        payment_method = _find_known_value(text, known_values["payment_methods"])
        if payment_method:
            filters["payment_method"] = payment_method

    if "income_expense" not in filters:
        income_expense = _find_known_value(text, known_values["income_expenses"])
        if income_expense:
            filters["income_expense"] = income_expense

    return filters


def _dimension_filter(filters):
    filters = filters or {}
    clauses = []
    params = {}

    if filters.get("sector"):
        clauses.append('AND "Sector" = %(sector)s')
        params["sector"] = filters["sector"]

    if filters.get("category"):
        clauses.append('AND "Categorization" = %(category)s')
        params["category"] = filters["category"]

    if filters.get("item_description"):
        clauses.append('AND "Item_Description" = %(item_description)s')
        params["item_description"] = filters["item_description"]

    if filters.get("payment_method"):
        clauses.append('AND "Payment_Method" = %(payment_method)s')
        params["payment_method"] = filters["payment_method"]

    if filters.get("income_expense"):
        clauses.append('AND "Income_Expense" = %(income_expense)s')
        params["income_expense"] = filters["income_expense"]

    return "\n          ".join(clauses), params


def _with_filters(result, filters):
    if filters:
        result["filters"] = dict(filters)
    return result


def normalize_period(question):
    text = question.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    words = text.split()

    for index, word in enumerate(words):
        month = MONTH_ALIASES.get(word)
        if not month:
            continue

        year = None
        nearby_words = words[max(0, index - 2):index + 3]
        for nearby_word in nearby_words:
            if re.fullmatch(r"\d{4}", nearby_word):
                year = int(nearby_word)
                break

        if year is None:
            year = date.today().year

        return f"month:{year}-{month:02d}"

    for word in words:
        if re.fullmatch(r"\d{4}", word):
            return f"year:{int(word)}"

    if "yesterday" in text:
        return "yesterday"
    if "today" in text:
        return "today"
    if "last week" in text or "previous week" in text:
        return "last_week"
    if "week" in text or "weekly" in text:
        return "this_week"
    if "last month" in text or "previous month" in text:
        return "last_month"
    if "month" in text or "monthly" in text:
        return "this_month"
    if "last year" in text or "previous year" in text:
        return "last_year"
    if "year" in text or "yearly" in text or "annual" in text:
        return "this_year"

    return "all_time"


def sales_total(period="all_time", filters=None):
    date_sql, params = _date_filter(period)
    filter_sql, filter_params = _dimension_filter(filters)
    params.update(filter_params)
    row = _fetch_one(
        f'''
        SELECT COALESCE(SUM("Amount"), 0) AS total_sales
        FROM {_table_ref()}
        WHERE COALESCE(__nc_deleted, false) = false
          AND "Income_Expense" = 'Income'
          {filter_sql}
          {date_sql}
        ''',
        params,
    )
    return _with_filters({
        "formula": "sales_total",
        "period": period,
        "total_sales": int(row["total_sales"] or 0),
    }, filters)


def expense_total(period="all_time", filters=None):
    date_sql, params = _date_filter(period)
    filter_sql, filter_params = _dimension_filter(filters)
    params.update(filter_params)
    row = _fetch_one(
        f'''
        SELECT
          COALESCE(SUM("Amount"), 0) AS total_expense,
          COUNT(*) AS expense_count,
          COUNT(*) FILTER (WHERE "Amount" IS NULL) AS missing_amount_count
        FROM {_table_ref()}
        WHERE COALESCE(__nc_deleted, false) = false
          AND "Income_Expense" = 'Expense'
          {filter_sql}
          {date_sql}
        ''',
        params,
    )
    return _with_filters({
        "formula": "expense_total",
        "period": period,
        "total_expense": int(row["total_expense"] or 0),
        "expense_count": int(row["expense_count"] or 0),
        "missing_amount_count": int(row["missing_amount_count"] or 0),
    }, filters)


def gross_profit(period="all_time", filters=None):
    date_sql, params = _date_filter(period)
    filter_sql, filter_params = _dimension_filter(filters)
    params.update(filter_params)
    row = _fetch_one(
        f'''
        SELECT
          COALESCE(SUM(CASE WHEN "Income_Expense" = 'Income' THEN "Amount" ELSE 0 END), 0) AS income,
          COALESCE(SUM(CASE WHEN "Income_Expense" = 'Expense' THEN "Amount" ELSE 0 END), 0) AS expense
        FROM {_table_ref()}
        WHERE COALESCE(__nc_deleted, false) = false
          {filter_sql}
          {date_sql}
        ''',
        params,
    )
    income = int(row["income"] or 0)
    expense = int(row["expense"] or 0)
    return _with_filters({
        "formula": "gross_profit",
        "period": period,
        "income": income,
        "expense": expense,
        "gross_profit": income - expense,
    }, filters)


def kpi_overview(period="all_time", filters=None):
    totals = gross_profit(period, filters)
    income = totals["income"]
    expense = totals["expense"]
    profit = totals["gross_profit"]
    margin = round((profit / income) * 100, 2) if income else 0

    return _with_filters({
        "formula": "kpi_overview",
        "period": period,
        "total_income": income,
        "total_expense": expense,
        "net_profit": profit,
        "profit_margin_percent": margin,
    }, filters)


def cash_flow(period="all_time", filters=None):
    date_sql, params = _date_filter(period)
    filter_sql, filter_params = _dimension_filter(filters)
    params.update(filter_params)
    rows = _fetch_all(
        f'''
        SELECT
          COALESCE("Payment_Method", 'Unknown') AS payment_method,
          COALESCE(SUM(CASE WHEN "Income_Expense" = 'Income' THEN "Amount" ELSE 0 END), 0) AS inflow,
          COALESCE(SUM(CASE WHEN "Income_Expense" = 'Expense' THEN "Amount" ELSE 0 END), 0) AS outflow
        FROM {_table_ref()}
        WHERE COALESCE(__nc_deleted, false) = false
          {filter_sql}
          {date_sql}
        GROUP BY COALESCE("Payment_Method", 'Unknown')
        ORDER BY payment_method
        ''',
        params,
    )

    methods = []
    total_inflow = 0
    total_outflow = 0

    for row in rows:
        inflow = int(row["inflow"] or 0)
        outflow = int(row["outflow"] or 0)
        total_inflow += inflow
        total_outflow += outflow
        methods.append({
            "payment_method": row["payment_method"],
            "inflow": inflow,
            "outflow": outflow,
            "net_cash_flow": inflow - outflow,
        })

    return _with_filters({
        "formula": "cash_flow",
        "period": period,
        "total_inflow": total_inflow,
        "total_outflow": total_outflow,
        "net_cash_flow": total_inflow - total_outflow,
        "by_payment_method": methods,
    }, filters)


def sector_summary(period="all_time", filters=None):
    date_sql, params = _date_filter(period)
    filter_sql, filter_params = _dimension_filter(filters)
    params.update(filter_params)
    rows = _fetch_all(
        f'''
        SELECT
          COALESCE("Sector", 'Unknown') AS sector,
          COALESCE(SUM(CASE WHEN "Income_Expense" = 'Income' THEN "Amount" ELSE 0 END), 0) AS income,
          COALESCE(SUM(CASE WHEN "Income_Expense" = 'Expense' THEN "Amount" ELSE 0 END), 0) AS expense
        FROM {_table_ref()}
        WHERE COALESCE(__nc_deleted, false) = false
          {filter_sql}
          {date_sql}
        GROUP BY COALESCE("Sector", 'Unknown')
        ORDER BY sector
        ''',
        params,
    )

    sectors = []
    for row in rows:
        income = int(row["income"] or 0)
        expense = int(row["expense"] or 0)
        sectors.append({
            "sector": row["sector"],
            "income": income,
            "expense": expense,
            "profit": income - expense,
        })

    return _with_filters({
        "formula": "sector_summary",
        "period": period,
        "sectors": sectors,
    }, filters)


def category_summary(period="all_time", filters=None):
    date_sql, params = _date_filter(period)
    filter_sql, filter_params = _dimension_filter(filters)
    params.update(filter_params)
    rows = _fetch_all(
        f'''
        SELECT
          COALESCE("Sector", 'Unknown') AS sector,
          COALESCE("Categorization", 'Unknown') AS category,
          COALESCE(SUM(CASE WHEN "Income_Expense" = 'Income' THEN "Amount" ELSE 0 END), 0) AS income,
          COALESCE(SUM(CASE WHEN "Income_Expense" = 'Expense' THEN "Amount" ELSE 0 END), 0) AS expense,
          COUNT(*) AS transaction_count
        FROM {_table_ref()}
        WHERE COALESCE(__nc_deleted, false) = false
          {filter_sql}
          {date_sql}
        GROUP BY COALESCE("Sector", 'Unknown'), COALESCE("Categorization", 'Unknown')
        ORDER BY sector, expense DESC, income DESC, category
        ''',
        params,
    )

    categories = []
    for row in rows:
        income = int(row["income"] or 0)
        expense = int(row["expense"] or 0)
        categories.append({
            "sector": row["sector"],
            "category": row["category"],
            "income": income,
            "expense": expense,
            "net": income - expense,
            "transaction_count": int(row["transaction_count"] or 0),
        })

    return _with_filters({
        "formula": "category_summary",
        "period": period,
        "categories": categories,
    }, filters)


def top_expenses(period="all_time", filters=None, limit=5):
    date_sql, params = _date_filter(period)
    filter_sql, filter_params = _dimension_filter(filters)
    params.update(filter_params)
    params["limit"] = limit
    rows = _fetch_all(
        f'''
        SELECT
          "Date",
          COALESCE("Sector", 'Unknown') AS sector,
          COALESCE("Categorization", 'Unknown') AS category,
          COALESCE("Item_Description", '') AS item,
          "Amount" AS amount,
          COALESCE("Payment_Method", 'Unknown') AS payment_method
        FROM {_table_ref()}
        WHERE COALESCE(__nc_deleted, false) = false
          AND "Income_Expense" = 'Expense'
          {filter_sql}
          {date_sql}
        ORDER BY "Amount" DESC
        LIMIT %(limit)s
        ''',
        params,
    )

    return _with_filters({
        "formula": "top_expenses",
        "period": period,
        "expenses": rows,
    }, filters)


FORMULAS = {
    "sales_total": sales_total,
    "expense_total": expense_total,
    "gross_profit": gross_profit,
    "kpi_overview": kpi_overview,
    "cash_flow": cash_flow,
    "sector_summary": sector_summary,
    "category_summary": category_summary,
    "top_expenses": top_expenses,
}


def choose_formula_by_keywords(question):
    text = question.lower()

    if "subgroup" in text or "sub group" in text or "transaction group" in text or "transection group" in text:
        return "category_summary"
    if "cash" in text or "cash flow" in text:
        return "cash_flow"
    if "top expense" in text or "biggest expense" in text or "largest expense" in text:
        return "top_expenses"
    if "expense" in text or "cost" in text or "spend" in text:
        return "expense_total"
    if (
        "category" in text
        or "categorization" in text
        or "machinery" in text
        or "machinary" in text
        or "equipment" in text
    ):
        return "category_summary"
    if "sector" in text or "group" in text:
        return "sector_summary"
    if "kpi" in text or "overview" in text or "margin" in text:
        return "kpi_overview"
    if "gross profit" in text or "net profit" in text or "profit" in text:
        return "gross_profit"
    if "sale" in text or "income" in text or "revenue" in text:
        return "sales_total"

    return None


def run_formula(formula_name, question):
    period = normalize_period(question)
    filters = extract_dimension_filters(question)
    formula = FORMULAS.get(formula_name, kpi_overview)
    return formula(period, filters)
