from datetime import date, datetime, time, timedelta
import logging
import re
import threading
from time import monotonic

import psycopg2
import psycopg2.extras

import config
from tools import search_intelligence
from tools.master_data import normalize_name


MONTH_ALIASES = {
    "jan": 1,
    "january": 1,
    "janurary": 1,
    "feb": 2,
    "february": 2,
    "febuary": 2,
    "feburary": 2,
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
MONTH_PATTERN = "|".join(sorted(MONTH_ALIASES, key=len, reverse=True))

SECTOR_ALIASES = {
    "farm": "Farm",
    "sp extension": "SP Extension",
    "extension": "SP Extension",
    "sp production": "SP Production",
    "production": "SP Production",
    "sotephwar": "Sote Phwar",
    "sote phwar": "Sote Phwar",
}

CATEGORY_ALIASES = {
    "machinery equipment and maintenance": "Machinery equipment and maintenance",
    "machinary equipment and maintenance": "Machinery equipment and maintenance",
    "machinery maintenance": "Machinery equipment and maintenance",
    "machinary maintenance": "Machinery equipment and maintenance",
    "machinery equipment": "Machinery equipment and maintenance",
    "machinary equipment": "Machinery equipment and maintenance",
    "machinery": "Machinery equipment and maintenance",
    "machinary": "Machinery equipment and maintenance",
    "agrochemical": "Agrochemical",
    "agrochemicals": "Agrochemical",
    "bonus labour": "Bonus for Labour",
    "bonus for labour": "Bonus for Labour",
}
_PAYMENT_SCHEMA_LOCK = threading.Lock()
_PAYMENT_RECEIVE_TABLE_READY = False
_VOUCHER_SUMMARY_FIELDS_READY = False

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
_TABLE_COLUMNS_CACHE = {}
logger = logging.getLogger(__name__)


def _table_ref():
    schema = config.TRANSACTION_SCHEMA.replace('"', '""')
    table = config.TRANSACTION_TABLE.replace('"', '""')
    return f'"{schema}"."{table}"'


def _sotephwar_transection_table_ref():
    schema = config.TRANSACTION_SCHEMA.replace('"', '""')
    table = getattr(
        config,
        "SOTEPHWAR_TRANSECTION_TABLE",
        "Sotephwar_Transection",
    ).replace('"', '""')
    return f'"{schema}"."{table}"'


def _farm_transection_table_ref():
    schema = config.TRANSACTION_SCHEMA.replace('"', '""')
    table = getattr(
        config,
        "FARM_TRANSECTION_TABLE",
        "farm_transection",
    ).replace('"', '""')
    return f'"{schema}"."{table}"'


def _sotephwar_inventory_table_ref():
    schema = config.TRANSACTION_SCHEMA.replace('"', '""')
    table = getattr(
        config,
        "SOTEPHWAR_INVENTORY_TABLE",
        "Sotephwar_Inventory",
    ).replace('"', '""')
    return f'"{schema}"."{table}"'


def _financial_obligations_table_ref():
    schema = config.TRANSACTION_SCHEMA.replace('"', '""')
    table = getattr(
        config,
        "FINANCIAL_OBLIGATIONS_TABLE",
        "Financial_Obligations",
    ).replace('"', '""')
    return f'"{schema}"."{table}"'


def _payment_receive_table_ref():
    schema = config.TRANSACTION_SCHEMA.replace('"', '""')
    table = getattr(
        config,
        "PAYMENT_RECEIVE_TABLE",
        "Payment_Receive",
    ).replace('"', '""')
    return f'"{schema}"."{table}"'


def _schema_ref(table):
    schema = config.TRANSACTION_SCHEMA.replace('"', '""')
    table = table.replace('"', '""')
    return f'"{schema}"."{table}"'


def _category_master_ref():
    return _schema_ref("category_master")


def _customer_master_ref():
    return _schema_ref("customer_master")


def _transaction_category_link_ref():
    return _schema_ref("_nc_m2m_Transection_category_master")


def _sotephwar_customer_link_ref():
    return _schema_ref("_nc_m2m_Sotephwar_Trans_customer_master")


def _farm_customer_link_ref():
    return _schema_ref("_nc_m2m_farm_transectio_customer_master")


def _linked_category_expr(table_alias="t"):
    alias = f'{table_alias}.' if table_alias else ""
    return f'COALESCE(cm."category_name", {alias}"Categorization")'


def _linked_customer_expr(table_alias="s"):
    alias = f'{table_alias}.' if table_alias else ""
    return f'COALESCE(cust."customer_name", {alias}"Customer_Name")'


def _linked_farm_customer_expr(table_alias="f"):
    alias = f'{table_alias}.' if table_alias else ""
    return f'COALESCE(cust."customer_name", {alias}"Customer")'


def _transaction_category_link_join(table_alias="t"):
    alias = table_alias
    return f'''
        LEFT JOIN LATERAL (
          SELECT cm_row."category_name"
          FROM {_transaction_category_link_ref()} tcm
          JOIN {_category_master_ref()} cm_row
            ON cm_row.id = tcm."category_master_id"
           AND COALESCE(cm_row.__nc_deleted, false) = false
          WHERE tcm."Transection_id" = {alias}.id
          ORDER BY cm_row.id
          LIMIT 1
        ) cm ON true
    '''


def _sotephwar_customer_link_join(table_alias="s"):
    alias = table_alias
    return f'''
        LEFT JOIN LATERAL (
          SELECT cust_row."customer_name"
          FROM {_sotephwar_customer_link_ref()} scm
          JOIN {_customer_master_ref()} cust_row
            ON cust_row.id = scm."customer_master_id"
           AND COALESCE(cust_row.__nc_deleted, false) = false
          WHERE scm."Sotephwar_Transection_id" = {alias}.id
          ORDER BY cust_row.id
          LIMIT 1
        ) cust ON true
    '''


def _farm_customer_link_join(table_alias="f"):
    alias = table_alias
    return f'''
        LEFT JOIN LATERAL (
          SELECT cust_row."customer_name"
          FROM {_farm_customer_link_ref()} fcm
          JOIN {_customer_master_ref()} cust_row
            ON cust_row.id = fcm."customer_master_id"
           AND COALESCE(cust_row.__nc_deleted, false) = false
          WHERE fcm."farm_transection_id" = {alias}.id
          ORDER BY cust_row.id
          LIMIT 1
        ) cust ON true
    '''


def _transaction_table_parts():
    return config.TRANSACTION_SCHEMA, config.TRANSACTION_TABLE


def _connect():
    options = []
    statement_timeout = getattr(config, "POSTGRES_STATEMENT_TIMEOUT_MS", 0)
    if statement_timeout:
        options.append(f"-c statement_timeout={int(statement_timeout)}")
    kwargs = {
        "host": config.POSTGRES_HOST,
        "database": config.POSTGRES_DB,
        "user": config.POSTGRES_USER,
        "password": config.POSTGRES_PASSWORD,
        "port": config.POSTGRES_PORT,
        "connect_timeout": getattr(config, "POSTGRES_CONNECT_TIMEOUT_SECONDS", 5),
    }
    if options:
        kwargs["options"] = " ".join(options)
    return psycopg2.connect(**kwargs)


def _fetch_all(sql, params=None):
    with _connect() as connection:
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(sql, params or {})
            return [dict(row) for row in cursor.fetchall()]


def _fetch_one(sql, params=None):
    rows = _fetch_all(sql, params)
    return rows[0] if rows else {}


def _execute(sql, params=None):
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(sql, params or {})


def _fetch_one_in_connection(connection, sql, params=None):
    with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute(sql, params or {})
        row = cursor.fetchone()
    return dict(row) if row else {}


def _fetch_all_in_connection(connection, sql, params=None):
    with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute(sql, params or {})
        return [dict(row) for row in cursor.fetchall()]


def _execute_in_connection(connection, sql, params=None):
    with connection.cursor() as cursor:
        cursor.execute(sql, params or {})


def _table_columns(schema, table):
    key = (schema, table)
    if key not in _TABLE_COLUMNS_CACHE:
        rows = _fetch_all(
            '''
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = %(schema)s
              AND table_name = %(table)s
            ''',
            {"schema": schema, "table": table},
        )
        _TABLE_COLUMNS_CACHE[key] = {row["column_name"] for row in rows}
    return _TABLE_COLUMNS_CACHE[key]


def _transaction_column_exists(column_name):
    schema, table = _transaction_table_parts()
    try:
        return column_name in _table_columns(schema, table)
    except Exception:
        return False


def _payment_receive_column_exists(column_name):
    schema = config.TRANSACTION_SCHEMA
    table = getattr(config, "PAYMENT_RECEIVE_TABLE", "Payment_Receive")
    try:
        return column_name in _table_columns(schema, table)
    except Exception:
        return False


def _schema_table_column_exists(table_name, column_name):
    try:
        return column_name in _table_columns(config.TRANSACTION_SCHEMA, table_name)
    except Exception:
        return False


def _period_dates(period):
    today = date.today()

    date_match = re.fullmatch(r"date:(\d{4})-(\d{2})-(\d{2})", period)
    range_match = re.fullmatch(r"range:(\d{4})-(\d{2})-(\d{2}):(\d{4})-(\d{2})-(\d{2})", period)
    month_match = re.fullmatch(r"month:(\d{4})-(\d{2})", period)
    year_match = re.fullmatch(r"year:(\d{4})", period)

    if date_match:
        start_date = date(
            int(date_match.group(1)),
            int(date_match.group(2)),
            int(date_match.group(3)),
        )
        end_date = start_date + timedelta(days=1)
    elif range_match:
        start_date = date(
            int(range_match.group(1)),
            int(range_match.group(2)),
            int(range_match.group(3)),
        )
        end_date = date(
            int(range_match.group(4)),
            int(range_match.group(5)),
            int(range_match.group(6)),
        ) + timedelta(days=1)
    elif month_match:
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
    return _date_filter_for_column(period, '"Date"')


def _date_filter_for_column(period, column_name):
    start, end = _period_dates(period)
    if start is None:
        return "", {}

    return f"AND {column_name} >= %(start)s AND {column_name} < %(end)s", {
        "start": start,
        "end": end,
    }


def _master_compare_granularity(question):
    text = _normalized_text(question)
    if any(_contains_phrase(text, phrase) for phrase in ("day by day", "daily", "by day")):
        return "day"
    if any(_contains_phrase(text, phrase) for phrase in ("week by week", "weekly", "by week")):
        return "week"
    if any(_contains_phrase(text, phrase) for phrase in ("month by month", "monthly", "by month")):
        return "month"
    if any(_contains_phrase(text, phrase) for phrase in ("year by year", "yearly", "by year")):
        return "year"
    return "month"


def _master_compare_scope(question):
    text = _normalized_text(question)
    has_category = "category" in text or "categories" in text or "category master" in text
    has_customer = "customer" in text or "customers" in text or "customer master" in text
    if has_category and not has_customer:
        return "category"
    if has_customer and not has_category:
        return "customer"
    return "both"


def _master_compare_period(question):
    text = _normalized_text(question)
    if _contains_phrase(text, "last year") or _contains_phrase(text, "previous year"):
        return "last_year"
    if _contains_phrase(text, "this year") or "yearly" in text or "annual" in text:
        return "this_year"
    if _contains_phrase(text, "last month") or _contains_phrase(text, "previous month"):
        return "last_month"
    if _contains_phrase(text, "this month"):
        return "this_month"
    if _contains_phrase(text, "last week") or _contains_phrase(text, "previous week"):
        return "last_week"
    if _contains_phrase(text, "this week"):
        return "this_week"
    return normalize_period(question)


def is_master_comparison_question(question):
    text = _normalized_text(question)
    return (
        ("master" in text or "category master" in text or "customer master" in text)
        and any(word in text for word in ("compare", "comparison", "report", "day", "week", "month", "year"))
        and ("category" in text or "customer" in text)
    )


def _normalized_text(text):
    return " ".join(re.sub(r"[^a-z0-9\s]", " ", text.lower()).split())


def _contains_phrase(text, phrase):
    return re.search(rf"(^|\s){re.escape(phrase)}($|\s)", text) is not None


def _loose_dimension_text(text):
    loose = _normalized_text(text)
    loose = re.sub(r"\bset\s+up\b", "setup", loose)
    loose = " ".join(word for word in loose.split() if not word.isdigit())
    return loose


def _searchable_transaction_text(text):
    return re.sub(r"\bset\s+up\b", "setup", _normalized_text(text))


TRANSACTION_SEARCH_STOPWORDS = {
    "show",
    "list",
    "tell",
    "me",
    "please",
    "transaction",
    "transactions",
    "transection",
    "transections",
    "record",
    "records",
    "detail",
    "details",
    "line",
    "lines",
    "all",
    "time",
    "today",
    "yesterday",
    "this",
    "last",
    "week",
    "month",
    "year",
    "monthly",
    "yearly",
    "date",
    "on",
    "in",
    "of",
    "for",
    "by",
    "from",
    "to",
    "and",
    "the",
    "top",
    "highest",
    "biggest",
    "largest",
    "total",
    "summary",
    "income",
    "incomes",
    "sale",
    "sales",
    "revenue",
    "expense",
    "expenses",
    "cost",
    "costs",
    "spend",
    "spending",
    "cash",
    "flow",
    "sector",
    "category",
    "categorization",
    "item",
    "items",
    "payment",
    "method",
}
TRANSACTION_SEARCH_STOPWORDS.update(MONTH_ALIASES)
TRANSACTION_SEARCH_STOPWORDS.update(_normalized_text(value) for value in SECTOR_ALIASES.values())
TRANSACTION_SEARCH_STOPWORDS.update(alias for alias in SECTOR_ALIASES)


def _transaction_search_terms(question, filters):
    text = _searchable_transaction_text(question)
    text = re.sub(r"\b\d{4}-\d{1,2}-\d{1,2}\b", " ", text)
    text = re.sub(r"\b\d{1,2}/\d{1,2}/\d{4}\b", " ", text)

    filter_values = set()
    for key in ("sector", "category", "income_expense", "payment_method"):
        value = filters.get(key)
        if value:
            filter_values.update(_normalized_text(value).split())

    terms = []
    for word in text.split():
        if word in TRANSACTION_SEARCH_STOPWORDS:
            continue
        if word in filter_values:
            continue
        if re.fullmatch(r"\d{4}", word):
            continue
        if word.isdigit():
            continue
        if len(word) < 2:
            continue
        terms.append(word)

    return list(dict.fromkeys(terms))


def clear_dimension_value_cache():
    _DIMENSION_VALUES_CACHE["expires_at"] = 0
    _DIMENSION_VALUES_CACHE["values"] = None


def _load_dimension_values():
    category_expr = _linked_category_expr("t")
    row = _fetch_one(
        f'''
        SELECT
          ARRAY_REMOVE(ARRAY_AGG(DISTINCT NULLIF(TRIM(t."Income_Expense"), '')), NULL) AS income_expenses,
          ARRAY_REMOVE(ARRAY_AGG(DISTINCT NULLIF(TRIM(t."Sector"), '')), NULL) AS sectors,
          ARRAY_REMOVE(ARRAY_AGG(DISTINCT NULLIF(TRIM({category_expr}), '')), NULL) AS categories,
          ARRAY_REMOVE(ARRAY_AGG(DISTINCT NULLIF(TRIM(t."Item_Description"), '')), NULL) AS item_descriptions,
          ARRAY_REMOVE(ARRAY_AGG(DISTINCT NULLIF(TRIM(t."Payment_Method"), '')), NULL) AS payment_methods
        FROM {_table_ref()} t
        {_transaction_category_link_join("t")}
        WHERE COALESCE(t.__nc_deleted, false) = false
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
    sorted_values = sorted(
        values,
        key=lambda item: len(_normalized_text(item)),
        reverse=True,
    )
    for value in sorted_values:
        normalized_value = _normalized_text(value).strip()
        if len(normalized_value) < 3 or normalized_value.isdigit():
            continue
        if normalized_value and _contains_phrase(text, normalized_value):
            return value
        loose_text = _loose_dimension_text(text)
        loose_value = _loose_dimension_text(value)
        if loose_value in MONTH_ALIASES or len(loose_value.split()) < 2:
            continue
        if loose_value and _contains_phrase(loose_text, loose_value):
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

    if "income_expense" not in filters and _contains_phrase(text, "expense"):
        filters["income_expense"] = "Expense"
    if "income_expense" not in filters and any(
        _contains_phrase(text, word)
        for word in ("income", "sale", "sales", "revenue")
    ):
        filters["income_expense"] = "Income"

    farm_customer = _farm_customer_filter(question) if filters.get("sector") in (None, "Farm") else None
    if farm_customer:
        filters["farm_customer"] = farm_customer

    text_search = _extract_transaction_text_search(question, filters)
    if text_search:
        filters["transaction_text_search"] = text_search

    return filters


def _extract_transaction_text_search(question, filters):
    text = _normalized_text(question)
    searchable_text = _searchable_transaction_text(question)

    has_setup_cost = (
        "setup" in searchable_text
        and ("cost" in text or "expense" in text or "spend" in text or "spending" in text)
    )
    if not has_setup_cost:
        if not (_detail_requested(question) or "search" in text or "find" in text):
            return None
        terms = _transaction_search_terms(question, filters)
        if not terms:
            return None
        return {"terms": terms}

    category = filters.get("category")
    category_search = _searchable_transaction_text(category) if category else None

    note_search = re.sub(
        r"\b(?:cost|costs|expense|expenses|spend|spending)\b",
        " ",
        category_search or searchable_text,
    )
    note_search = " ".join(note_search.split())

    if len(note_search) < 3:
        return None

    return {
        "category": category_search or note_search,
        "note": note_search,
    }


FARM_CUSTOMER_STOP_WORDS = (
    "show|find|tell|me|please|customer|from|for|by|farm|section|sections|"
    "sale|sales|income|revenue|total|summary|summaries|report|reports|"
    "top|biggest|largest|highest|this|last|year|month|week|today|yesterday"
)


def _farm_customer_filter(question):
    text = _normalized_text(question)
    if any(_contains_phrase(text, word) for word in ("expense", "cost", "spend", "spending")):
        return None

    has_income_word = any(_contains_phrase(text, word) for word in ("sale", "sales", "income", "revenue"))
    if has_income_word:
        cleaned = re.sub(rf"\b(?:{FARM_CUSTOMER_STOP_WORDS})\b", " ", text)
        cleaned = re.sub(rf"\b(?:{MONTH_PATTERN})\b", " ", cleaned)
        cleaned = re.sub(r"\b\d{4}\b", " ", cleaned)
        cleaned = " ".join(word for word in cleaned.split() if len(word) > 1 and not word.isdigit())
        sector_names = {_normalized_text(value) for value in SECTOR_ALIASES.values()} | set(SECTOR_ALIASES)
        if cleaned and cleaned not in sector_names:
            return cleaned

    return _known_farm_customer_filter(question)


def _known_farm_customer_filter(question):
    query = _normalized_text(question)
    if not query or len(query) < 3:
        return None
    query = re.sub(rf"\b(?:{FARM_CUSTOMER_STOP_WORDS})\b", " ", query)
    query = re.sub(rf"\b(?:{MONTH_PATTERN})\b", " ", query)
    query = re.sub(r"\b\d{4}\b", " ", query)
    query = " ".join(word for word in query.split() if len(word) > 1 and not word.isdigit())
    if not query:
        return None
    try:
        rows = _fetch_all(
            f'''
            SELECT DISTINCT {_linked_farm_customer_expr("f")} AS customer
            FROM {_farm_transection_table_ref()} f
            {_farm_customer_link_join("f")}
            WHERE COALESCE(f.__nc_deleted, false) = false
              AND NULLIF(TRIM({_linked_farm_customer_expr("f")}), '') IS NOT NULL
            ''',
        )
    except Exception:
        return None

    normalized_query = normalize_name(query)
    for row in rows:
        customer = row.get("customer")
        if normalize_name(customer) == normalized_query:
            return normalized_query
    return None


def _dimension_filter(filters):
    filters = filters or {}
    clauses = []
    params = {}

    if filters.get("sector"):
        clauses.append('AND "Sector" = %(sector)s')
        params["sector"] = filters["sector"]

    text_search = filters.get("transaction_text_search")

    if filters.get("categories") and not text_search:
        category_values = [category for category in filters["categories"] if category]
        if category_values:
            placeholders = []
            for index, category in enumerate(category_values):
                param_name = f"category_{index}"
                placeholders.append(f"%({param_name})s")
                params[param_name] = normalize_name(category)
            clauses.append(f"AND {_category_normalized_sql()} IN ({', '.join(placeholders)})")

    if filters.get("category") and not text_search:
        clauses.append(f"AND {_category_normalized_sql()} = %(category)s")
        params["category"] = normalize_name(filters["category"])

    if filters.get("item_description") and not text_search:
        clauses.append('AND "Item_Description" = %(item_description)s')
        params["item_description"] = filters["item_description"]

    if filters.get("payment_method"):
        clauses.append('AND "Payment_Method" = %(payment_method)s')
        params["payment_method"] = filters["payment_method"]

    if filters.get("income_expense"):
        clauses.append('AND "Income_Expense" = %(income_expense)s')
        params["income_expense"] = filters["income_expense"]

    if text_search:
        search_clauses = [
            f"{_category_search_sql()} LIKE %(transaction_category_search)s",
            'REPLACE(LOWER(COALESCE("Item_Description", \'\')), \'set up\', \'setup\') LIKE %(transaction_note_search)s',
        ]
        if _transaction_column_exists("Note"):
            search_clauses.append(
                'REPLACE(LOWER(COALESCE("Note", \'\')), \'set up\', \'setup\') LIKE %(transaction_note_search)s'
            )
        if _transaction_column_exists("AI_Comment"):
            search_clauses.append(
                'REPLACE(LOWER(COALESCE("AI_Comment", \'\')), \'set up\', \'setup\') LIKE %(transaction_note_search)s'
            )
        if text_search.get("category") and text_search.get("note"):
            clauses.append(f"AND ({' OR '.join(search_clauses)})")
            params["transaction_category_search"] = f"%{text_search['category']}%"
            params["transaction_note_search"] = f"%{text_search['note']}%"

        keyword_columns = [
            _category_keyword_sql(),
            'LOWER(COALESCE("Item_Description", \'\'))',
        ]
        if _transaction_column_exists("Note"):
            keyword_columns.append('LOWER(COALESCE("Note", \'\'))')
        if _transaction_column_exists("AI_Comment"):
            keyword_columns.append('LOWER(COALESCE("AI_Comment", \'\'))')
        for index, term in enumerate(text_search.get("terms") or []):
            param_name = f"transaction_text_search_{index}"
            clauses.append(
                "AND ("
                + " OR ".join(f"{column} LIKE %({param_name})s" for column in keyword_columns)
                + ")"
            )
            params[param_name] = f"%{term}%"

    return "\n          ".join(clauses), params


def _category_normalized_sql():
    category = _linked_category_expr("t")
    return (
        "TRIM(REGEXP_REPLACE("
        "REPLACE("
        "REGEXP_REPLACE("
        f"REGEXP_REPLACE(LOWER(COALESCE({category}, '')), '[_\\-–—]+', ' ', 'g'), "
        "'[^a-z0-9\\s]', ' ', 'g'"
        "), "
        "'set up', 'setup'"
        "), "
        "'\\s+', ' ', 'g'"
        "))"
    )


def _category_search_sql():
    return (
        "REPLACE("
        "LOWER(COALESCE("
        f"{_linked_category_expr('t')}, ''"
        ")), 'set up', 'setup')"
    )


def _category_keyword_sql():
    return f"LOWER(COALESCE({_linked_category_expr('t')}, ''))"


def _customer_normalized_sql():
    customer = _linked_customer_expr("s")
    return (
        "TRIM(REGEXP_REPLACE("
        "REPLACE("
        "REGEXP_REPLACE("
        f"REGEXP_REPLACE(LOWER(COALESCE({customer}, '')), '[_\\-–—]+', ' ', 'g'), "
        "'[^a-z0-9\\s]', ' ', 'g'"
        "), "
        "'set up', 'setup'"
        "), "
        "'\\s+', ' ', 'g'"
        "))"
    )


def _farm_customer_normalized_sql():
    customer = _linked_farm_customer_expr("f")
    return (
        "TRIM(REGEXP_REPLACE("
        "REPLACE("
        "REGEXP_REPLACE("
        f"REGEXP_REPLACE(LOWER(COALESCE({customer}, '')), '[_\\-–—]+', ' ', 'g'), "
        "'[^a-z0-9\\s]', ' ', 'g'"
        "), "
        "'set up', 'setup'"
        "), "
        "'\\s+', ' ', 'g'"
        "))"
    )


def _include_farm_sales(filters):
    filters = filters or {}
    if filters.get("income_expense") == "Expense":
        return False
    if filters.get("sector") and filters["sector"] != "Farm":
        return False
    if filters.get("category") or filters.get("categories"):
        return False
    if filters.get("item_description") or filters.get("payment_method"):
        return False
    if filters.get("transaction_text_search"):
        return False
    return True


def _include_sotephwar_income(filters):
    filters = filters or {}
    if filters.get("farm_customer"):
        return False
    if filters.get("income_expense") == "Expense":
        return False
    if filters.get("sector") and filters["sector"] != "Sote Phwar":
        return False
    if filters.get("category") or filters.get("categories"):
        return False
    if filters.get("item_description") or filters.get("payment_method"):
        return False
    if filters.get("transaction_text_search"):
        return False
    return True


def _include_transaction_rows(filters):
    filters = filters or {}
    return not filters.get("farm_customer")


def _canonical_transection_income_condition(alias="t"):
    return f'''
      NOT (
        {alias}."Income_Expense" = 'Income'
        AND LOWER(TRIM(COALESCE({alias}."Sector", ''))) IN ('sote phwar', 'sotephwar')
      )
    '''


def _farm_filter(period, filters):
    date_sql, params = _date_filter_for_column(period, 'f."Date"')
    clauses = []
    filters = filters or {}
    if filters.get("farm_customer"):
        clauses.append(f"AND {_farm_customer_normalized_sql()} = %(farm_customer)s")
        params["farm_customer"] = normalize_name(filters["farm_customer"])
    return "\n          ".join(clauses), date_sql, params


def _farm_sales_total(period, filters=None):
    return _farm_sales_summary(period, filters)["total_amount"]


def _farm_sales_summary(period, filters=None):
    empty = {
        "invoice_count": 0,
        "total_amount": 0,
        "amount_received": 0,
        "outstanding_amount": 0,
    }
    if not _include_farm_sales(filters):
        return empty
    farm_filter_sql, date_sql, params = _farm_filter(period, filters)
    row = _fetch_one(
        f'''
        SELECT
          COUNT(*) AS invoice_count,
          COALESCE(SUM(f."Total_Amount"), 0) AS total_amount,
          COALESCE(SUM(f."Total_Received"), 0) AS amount_received,
          COALESCE(SUM(f."Outstanding_Balance"), 0) AS outstanding_amount
        FROM {_farm_transection_table_ref()} f
        {_farm_customer_link_join("f")}
        WHERE COALESCE(f.__nc_deleted, false) = false
          {farm_filter_sql}
          {date_sql}
        ''',
        params,
    )
    return {
        "invoice_count": int(row.get("invoice_count") or 0),
        "total_amount": int(row.get("total_amount") or 0),
        "amount_received": int(row.get("amount_received") or 0),
        "outstanding_amount": int(row.get("outstanding_amount") or 0),
    }


def _sotephwar_income_summary(period, filters=None):
    empty = {
        "invoice_count": 0,
        "total_amount": 0,
        "amount_received": 0,
        "outstanding_amount": 0,
        "customers": [],
    }
    if not _include_sotephwar_income(filters):
        return empty
    result = sotephwar_transection_summary(period, include_customers=False)
    return {
        "invoice_count": int(result.get("invoice_count") or 0),
        "total_amount": int(result.get("total_amount") or 0),
        "amount_received": int(result.get("amount_received") or 0),
        "outstanding_amount": int(result.get("outstanding_amount") or 0),
        "customers": [],
    }


def _farm_sales_rows(period, filters=None, limit=5):
    if not _include_farm_sales(filters):
        return []
    farm_filter_sql, date_sql, params = _farm_filter(period, filters)
    if limit is not None:
        params["limit"] = limit
        limit_sql = "LIMIT %(limit)s"
    else:
        limit_sql = ""
    rows = _fetch_all(
        f'''
        SELECT
          'Farm' AS sector,
          'Farm Sales' AS category,
          MIN(COALESCE({_linked_farm_customer_expr("f")}, '')) AS item,
          MIN(COALESCE({_linked_farm_customer_expr("f")}, '')) AS customer_name,
          COALESCE(SUM(f."Total_Amount"), 0) AS amount,
          COALESCE(SUM(f."Total_Amount"), 0) AS total_amount,
          COALESCE(SUM(f."Total_Received"), 0) AS amount_received,
          COALESCE(SUM(f."Outstanding_Balance"), 0) AS outstanding_amount,
          COUNT(*) AS invoice_count,
          'Farm_Transection' AS payment_method
        FROM {_farm_transection_table_ref()} f
        {_farm_customer_link_join("f")}
        WHERE COALESCE(f.__nc_deleted, false) = false
          AND f."Total_Amount" IS NOT NULL
          {farm_filter_sql}
          {date_sql}
        GROUP BY {_farm_customer_normalized_sql()}
        ORDER BY amount DESC NULLS LAST
        {limit_sql}
        ''',
        params,
    )
    for row in rows:
        row["amount"] = int(row["amount"] or 0)
        row["total_amount"] = int(row.get("total_amount") or 0)
        row["amount_received"] = int(row.get("amount_received") or 0)
        row["outstanding_amount"] = int(row.get("outstanding_amount") or 0)
        row["invoice_count"] = int(row.get("invoice_count") or 0)
    return rows


def farm_transection_customer(period="all_time", customer=None, limit=50):
    filters = {}
    if customer:
        filters["farm_customer"] = customer
    farm_filter_sql, date_sql, params = _farm_filter(period, filters)
    params["limit"] = limit

    rows = _fetch_all(
        f'''
        SELECT
          f."Date" AS invoice_date,
          COALESCE(f."Invoice_Number"::text, '') AS invoice_number,
          COALESCE({_linked_farm_customer_expr("f")}, '') AS customer_name,
          COALESCE(f."Note", '') AS note,
          COALESCE(f."Total_Amount", 0) AS total_amount,
          COALESCE(f."Total_Received", 0) AS amount_received,
          COALESCE(f."Outstanding_Balance", 0) AS outstanding_amount
        FROM {_farm_transection_table_ref()} f
        {_farm_customer_link_join("f")}
        WHERE COALESCE(f.__nc_deleted, false) = false
          AND f."Total_Amount" IS NOT NULL
          {farm_filter_sql}
          {date_sql}
        ORDER BY f."Date" DESC NULLS LAST, f."Invoice_Number" DESC NULLS LAST, f.id DESC
        LIMIT %(limit)s
        ''',
        params,
    )

    total_amount = 0
    amount_received = 0
    outstanding_amount = 0
    for row in rows:
        row["item"] = "Farm Sales"
        row["quantity"] = 0
        row["total_amount"] = int(row["total_amount"] or 0)
        row["amount_received"] = int(row["amount_received"] or 0)
        row["outstanding_amount"] = int(row["outstanding_amount"] or 0)
        total_amount += row["total_amount"]
        amount_received += row["amount_received"]
        outstanding_amount += row["outstanding_amount"]

    return _with_filters({
        "formula": "farm_transection_customer",
        "period": period,
        "customer": customer,
        "invoice_count": len(rows),
        "total_sales": total_amount,
        "amount_received": amount_received,
        "outstanding_amount": outstanding_amount,
        "invoices": rows,
    }, filters)


def _sotephwar_income_rows(period, filters=None, limit=5):
    if not _include_sotephwar_income(filters):
        return []
    date_sql, params = _date_filter_for_column(period, 's."Invoice_Date"')
    if limit is not None:
        params["limit"] = limit
        limit_sql = "LIMIT %(limit)s"
    else:
        limit_sql = ""
    rows = _fetch_all(
        f'''
        SELECT
          'Sote Phwar' AS sector,
          'Sote Phwar Sales' AS category,
          COALESCE({_linked_customer_expr("s")}, '') AS item,
          COALESCE({_linked_customer_expr("s")}, '') AS customer_name,
          COALESCE(SUM(s."Total_Amount"), 0) AS amount,
          COALESCE(SUM(s."Total_Amount"), 0) AS total_amount,
          COALESCE(SUM(s."Total_Received"), 0) AS amount_received,
          COALESCE(SUM(s."Outstanding_Balance"), 0) AS outstanding_amount,
          COUNT(*) AS invoice_count,
          'Sotephwar_Transection' AS payment_method
        FROM {_sotephwar_transection_table_ref()} s
        {_sotephwar_customer_link_join("s")}
        WHERE COALESCE(s.__nc_deleted, false) = false
          AND s."Total_Amount" IS NOT NULL
          {date_sql}
        GROUP BY COALESCE({_linked_customer_expr("s")}, '')
        ORDER BY amount DESC NULLS LAST
        {limit_sql}
        ''',
        params,
    )
    for row in rows:
        row["amount"] = int(row["amount"] or 0)
        row["total_amount"] = int(row.get("total_amount") or 0)
        row["amount_received"] = int(row.get("amount_received") or 0)
        row["outstanding_amount"] = int(row.get("outstanding_amount") or 0)
        row["invoice_count"] = int(row.get("invoice_count") or 0)
    return rows


def _farm_cash_flow(period, filters=None):
    if not _include_farm_sales(filters):
        return 0
    farm_filter_sql, date_sql, params = _farm_filter(period, filters)
    row = _fetch_one(
        f'''
        SELECT COALESCE(SUM(f."Total_Received"), 0) AS total_received
        FROM {_farm_transection_table_ref()} f
        {_farm_customer_link_join("f")}
        WHERE COALESCE(f.__nc_deleted, false) = false
          {farm_filter_sql}
          {date_sql}
        ''',
        params,
    )
    return int(row.get("total_received") or 0)


def _with_filters(result, filters):
    if filters:
        result["filters"] = dict(filters)
    return result


def is_sotephwar_transection_question(question):
    text = _normalized_text(question)
    return (
        "sotephwar transection" in text
        or "sotephwar transaction" in text
        or "sote phwar transection" in text
        or "sote phwar transaction" in text
        or "sotephwar table" in text
        or "sote phwar table" in text
    )


def is_sotephwar_inventory_question(question):
    if is_sotephwar_transection_question(question):
        return False

    text = _normalized_text(question)
    return (
        ("sotephwar" in text or "sote phwar" in text)
        and (
            any(
                word in text
                for word in (
                    "inventory",
                    "stock",
                    "store",
                    "movement",
                    "movements",
                    "production",
                    "transfer",
                    "transfers",
                )
            )
            or (
                _sotephwar_item_filter(question)
                and ("quantity" in text or "qty" in text or "bottle" in text or "bottles" in text)
            )
        )
    )


def _mentions_sotephwar(question):
    text = _normalized_text(question)
    return "sotephwar" in text or "sote phwar" in text


def _sotephwar_unpaid_filter(question):
    text = _normalized_text(question)
    return (
        "unpaid" in text
        or "outstanding" in text
        or "amount remained" in text
        or "amount remain" in text
        or "debt" in text
        or "receivable" in text
        or "not yet received" in text
        or "not received" in text
        or "still has" in text
    )


def _sotephwar_note_requested(question):
    text = _normalized_text(question)
    return "note" in text or "notes" in text


def _sotephwar_voucher_question(question):
    text = _normalized_text(question)
    return _mentions_sotephwar(question) and (
        "voucher" in text
        or "invoice" in text
        or "customer" in text
        or _sotephwar_unpaid_filter(question)
    )


def _month_by_month_requested(question):
    text = _normalized_text(question)
    return (
        "month by month" in text
        or "monthly" in text
        or "each month" in text
        or "by month" in text
        or "month wise" in text
        or "monthwise" in text
    )


def _sotephwar_income_summary_question(question):
    text = _normalized_text(question)
    if not _mentions_sotephwar(question):
        return False
    return any(
        word in text
        for word in (
            "income",
            "imcome",
            "sale",
            "sales",
            "revenue",
            "summary",
            "total",
            "amount",
        )
    )


def _sotephwar_invoice_numbers(question):
    text = _normalized_text(question)
    matches = []
    for match in re.finditer(r"\b(?:voucher|invoice)(?:\s+(?:number|no))?\s+((?:\d+\s*)+(?:and\s+\d+\s*)*)", text):
        matches.extend(re.findall(r"\d+", match.group(1)))
    return list(dict.fromkeys(matches))


def _sotephwar_payment_update_requested(question):
    text = _normalized_text(question)
    words = set(text.split())
    return (
        _mentions_sotephwar(question)
        and ("voucher" in text or "invoice" in text)
        and bool(words & {"got", "received", "receive", "paid", "payment"})
    )


def _parse_sotephwar_payment_update(question):
    text = _normalized_text(question)
    raw_text = question.lower()
    invoice_numbers = _sotephwar_invoice_numbers(question)
    invoice_number = invoice_numbers[0] if invoice_numbers else None

    amount = None
    amount_match = re.search(
        r"\b(?:got|received|receive|paid|payment|amount received)\s+([\d,]+)\s*(?:kyat|kyats|mmk)?\b",
        raw_text,
    )
    if amount_match:
        amount = int(amount_match.group(1).replace(",", ""))
    else:
        numbers = re.findall(r"\b\d[\d,]*\b", text)
        if invoice_number:
            numbers = [number for number in numbers if number.replace(",", "") != invoice_number]
        if numbers:
            amount = int(numbers[-1].replace(",", ""))

    period = normalize_period(question)
    received_date = None
    if period.startswith("date:"):
        received_date = _parse_date_value(period.replace("date:", ""))
    if received_date is None:
        received_date = date.today()

    return {
        "invoice_number": invoice_number,
        "amount": amount,
        "received_date": received_date,
    }


def _detail_requested(question):
    text = _normalized_text(question)
    return (
        "detail" in text
        or "details" in text
        or "line" in text
        or "lines" in text
        or "each transaction" in text
        or "each transection" in text
        or "transaction line" in text
        or "transection line" in text
        or "record" in text
        or "records" in text
        or "list" in text
    )


SOTEPHWAR_CUSTOMER_STOPWORDS = {
    "show",
    "list",
    "tell",
    "me",
    "please",
    "sotephwar",
    "sote",
    "phwar",
    "transection",
    "transaction",
    "table",
    "voucher",
    "vouchers",
    "invoice",
    "invoices",
    "customer",
    "customers",
    "name",
    "by",
    "for",
    "of",
    "from",
    "in",
    "the",
    "unpaid",
    "outstanding",
    "amount",
    "remained",
    "remain",
    "debt",
    "receivable",
    "note",
    "notes",
    "report",
    "and",
}
SOTEPHWAR_CUSTOMER_STOPWORDS.update(MONTH_ALIASES)


def _sotephwar_customer_search_text(question):
    words = [
        word
        for word in _normalized_text(question).split()
        if word not in SOTEPHWAR_CUSTOMER_STOPWORDS and not word.isdigit()
    ]
    return " ".join(words)


def _sotephwar_item_filter(question):
    text = _normalized_text(question)
    if re.search(r"(^|\s)4\s*l($|\s)", text) or "4l" in text:
        return "Sote Phwar 4L"
    if re.search(r"(^|\s)1\s*l($|\s)", text) or "1l" in text:
        return "Sote Phwar 1L"
    if "500 ml" in text or "500ml" in text or "500 m l" in text:
        return "Sote Phwar 500 mL"
    if "100 ml" in text or "100ml" in text or "100 m l" in text:
        return "Sote Phwar 100 mL"
    return None


def _sotephwar_inventory_store_filter(question):
    text = _normalized_text(question)
    known_aliases = {
        "factory": "Factory",
        "heho": "Heho Store (Home)",
        "home": "Heho Store (Home)",
        "myint thar": "Myint Thar Store",
        "myit thar": "Myint Thar Store",
        "myint thar store": "Myint Thar Store",
        "myit thar store": "Myint Thar Store",
    }
    for alias, store in known_aliases.items():
        if _contains_phrase(text, alias):
            return store

    try:
        rows = _fetch_all(
            f'''
            SELECT DISTINCT store_name
            FROM (
              SELECT "From_Store" AS store_name FROM {_sotephwar_inventory_table_ref()}
              UNION
              SELECT "To_Store" AS store_name FROM {_sotephwar_inventory_table_ref()}
            ) stores
            WHERE store_name IS NOT NULL
              AND store_name NOT IN ('-', 'Customer')
            '''
        )
    except Exception:
        return None

    for row in rows:
        store_name = row.get("store_name") or ""
        normalized_store = _normalized_text(store_name)
        if normalized_store and _contains_phrase(text, normalized_store):
            return store_name

    return None


def _sotephwar_inventory_store_values(store):
    if store == "Myint Thar Store":
        return ["Myint Thar Store", "Myit Thar Store"]
    return [store]


def _sotephwar_inventory_store_expr(column_name):
    return f"CASE WHEN {column_name} = 'Myit Thar Store' THEN 'Myint Thar Store' ELSE {column_name} END"


def _sotephwar_inventory_type_filter(question):
    text = _normalized_text(question)
    if "production" in text or "produce" in text:
        return "Production"
    if "transfer" in text or "transfers" in text:
        return "Transfer"
    if "sale" in text or "sales" in text or "sell" in text or "sold" in text:
        return "Sale"
    return None


def is_financial_obligation_question(question):
    text = _normalized_text(question)
    return any(
        phrase in text
        for phrase in (
            "financial obligation",
            "financial obligations",
            "obligation",
            "obligations",
            "loan due",
            "loan dues",
            "debt due",
            "payable",
            "payables",
        )
    )


def _financial_obligation_insert_requested(question):
    text = _normalized_text(question)
    return is_financial_obligation_question(question) and (
        text.startswith("add ")
        or text.startswith("insert ")
        or text.startswith("create ")
    )


def _financial_obligation_status_filter(question):
    text = _normalized_text(question)
    if "inactive" in text or "closed" in text or "paid off" in text:
        return "Inactive"
    if "active" in text or "open" in text:
        return "Active"
    return None


def _financial_obligation_category_filter(question):
    text = _normalized_text(question)
    match = re.search(r"\bcategory\s+([a-z0-9][a-z0-9\s-]{1,40})", text)
    if match:
        return match.group(1).strip()
    for category in ("loan", "rent", "salary", "tax", "interest", "payable"):
        if _contains_phrase(text, category):
            return category
    return None


def _financial_obligation_creditor_filter(question):
    text = _normalized_text(question)
    match = re.search(r"\b(?:creditor|for|to)\s+([a-z0-9][a-z0-9\s.,-]{1,60})", text)
    if not match:
        return None
    value = match.group(1)
    value = re.split(
        r"\b(?:amount|category|subcategory|frequency|start|due|next due|status|notes?)\b",
        value,
        maxsplit=1,
    )[0]
    return " ".join(value.split()).strip(" .,") or None


def _financial_obligation_due_days(question):
    text = _normalized_text(question)
    if "overdue" in text:
        return 0
    match = re.search(r"\b(?:next|due in)\s+(\d{1,3})\s+days?\b", text)
    if match:
        return max(0, min(int(match.group(1)), 365))
    if "this week" in text:
        return 7
    if "this month" in text or "due soon" in text or "upcoming" in text:
        return 30
    return 30


def _extract_field_value(question, labels):
    label_pattern = "|".join(re.escape(label) for label in labels)
    all_labels = (
        "creditor", "amount", "category", "subcategory", "frequency",
        "start", "start date", "due", "next due", "next due date",
        "status", "note", "notes",
    )
    stop_pattern = "|".join(re.escape(label) for label in all_labels)
    match = re.search(
        rf"\b(?:{label_pattern})\s*[:=]?\s*(.+?)(?=\s+\b(?:{stop_pattern})\b\s*[:=]?|$)",
        question,
        re.IGNORECASE,
    )
    if not match:
        return None
    return " ".join(match.group(1).strip(" .,").split()) or None


def _parse_date_value(value):
    if not value:
        return None
    match = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", value)
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def _parse_financial_obligation_insert(question):
    amount_text = _extract_field_value(question, ("amount",))
    amount_match = re.search(r"[\d,]+", amount_text or "")
    amount = int(amount_match.group(0).replace(",", "")) if amount_match else None
    creditor = _extract_field_value(question, ("creditor",))
    next_due_date = _parse_date_value(_extract_field_value(question, ("next due date", "next due", "due")))
    start_date = _parse_date_value(_extract_field_value(question, ("start date", "start")))

    return {
        "category": _extract_field_value(question, ("category",)) or "Loan",
        "subcategory": _extract_field_value(question, ("subcategory",)) or "",
        "creditor": creditor,
        "amount": amount,
        "frequency": _extract_field_value(question, ("frequency",)) or "",
        "start_date": start_date,
        "next_due_date": next_due_date,
        "status": _extract_field_value(question, ("status",)) or "Active",
        "notes": _extract_field_value(question, ("notes", "note")) or "",
    }


def is_payment_receive_question(question):
    text = _normalized_text(question)
    return any(
        phrase in text
        for phrase in (
            "payment receive",
            "receive payment",
            "received payment",
            "payment received",
            "collection rate",
            "receivable summary",
            "receivables summary",
            "outstanding receivable",
            "outstanding receivables",
            "customer balance",
            "customer balances",
            "aging analysis",
            "ageing analysis",
            "receivable aging",
            "receivable ageing",
        )
    )


def _payment_receive_insert_requested(question):
    text = _normalized_text(question)
    words = set(text.split())
    return is_payment_receive_question(question) and (
        ("voucher" in words or "invoice" in words)
        and bool(words & {"amount", "receive", "received", "payment", "paid", "got"})
    )


def _normalize_payment_sector(value):
    text = _normalized_text(value or "")
    if _contains_phrase(text, "farm"):
        return "Farm"
    if (
        _contains_phrase(text, "sotephwar")
        or _contains_phrase(text, "sote phwar")
        or _contains_phrase(text, "sp extension")
        or _contains_phrase(text, "extension")
        or _contains_phrase(text, "sp production")
        or _contains_phrase(text, "production")
    ):
        return "Sote Phwar"
    return None


def _payment_field_value(question, labels):
    label_pattern = "|".join(re.escape(label) for label in labels)
    all_labels = (
        "sector", "voucher", "voucher number", "voucher no", "invoice",
        "invoice number", "invoice no", "amount", "receive amount",
        "received amount", "payment amount", "method", "payment method",
        "ref", "reference", "reference number", "notes", "note",
        "recorded by", "user", "date", "receive date",
    )
    stop_pattern = "|".join(re.escape(label) for label in all_labels)
    match = re.search(
        rf"\b(?:{label_pattern})\s*[:=]?\s*(.+?)(?=\s+\b(?:{stop_pattern})\b\s*[:=]?|$)",
        question,
        re.IGNORECASE,
    )
    if not match:
        return None
    return " ".join(match.group(1).strip(" .,").split()) or None


def _parse_payment_receive(question):
    sector = _normalize_payment_sector(_payment_field_value(question, ("sector",)) or question)

    voucher = _payment_field_value(
        question,
        ("voucher number", "voucher no", "voucher", "invoice number", "invoice no", "invoice"),
    )
    if voucher:
        voucher = re.split(
            r"\b(?:amount|receive|received|payment|method|ref|reference|notes?|recorded by|date)\b",
            voucher,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0].strip(" .,")
    if not voucher:
        match = re.search(
            r"\b(?:voucher|invoice)(?:\s+(?:number|no))?\s*[:=]?\s*([A-Za-z0-9._/-]+)",
            question,
            re.IGNORECASE,
        )
        voucher = match.group(1).strip(" .,") if match else None

    amount_text = _payment_field_value(
        question,
        ("receive amount", "received amount", "payment amount", "amount"),
    )
    amount_match = re.search(r"\d[\d,]*", amount_text or "")
    amount = int(amount_match.group(0).replace(",", "")) if amount_match else None
    if amount is None:
        raw_numbers = re.findall(r"\b\d[\d,]*\b", question)
        voucher_digits = re.sub(r"\D", "", voucher or "")
        amount_candidates = [
            number for number in raw_numbers
            if number.replace(",", "") != voucher_digits
        ]
        if amount_candidates:
            amount = int(amount_candidates[-1].replace(",", ""))

    period = normalize_period(question)
    receive_date = _parse_date_value(period.replace("date:", "")) if period.startswith("date:") else None

    return {
        "receive_date": receive_date or date.today(),
        "sector": sector,
        "voucher_number": voucher,
        "receive_amount": amount,
        "payment_method": _payment_field_value(question, ("payment method", "method")) or "",
        "reference_number": _payment_field_value(question, ("reference number", "reference", "ref")) or "",
        "notes": _payment_field_value(question, ("notes", "note")) or "",
        "recorded_by": _payment_field_value(question, ("recorded by", "user")) or "",
    }


def _sotephwar_customer_match(question):
    try:
        rows = _fetch_all(
            f'''
            SELECT DISTINCT {_linked_customer_expr("s")} AS customer_name
            FROM {_sotephwar_transection_table_ref()} s
            {_sotephwar_customer_link_join("s")}
            WHERE COALESCE(s.__nc_deleted, false) = false
              AND NULLIF(TRIM({_linked_customer_expr("s")}), '') IS NOT NULL
            ORDER BY customer_name
            '''
        )
    except Exception:
        return search_intelligence.SearchMatch(
            None,
            "none",
            "customer lookup failed",
            _sotephwar_customer_search_text(question),
        )

    return search_intelligence.match_name(
        question,
        [row["customer_name"] for row in rows],
        stopwords=SOTEPHWAR_CUSTOMER_STOPWORDS,
    )


def _sotephwar_customer_filter(question):
    match = _sotephwar_customer_match(question)
    if match.safe:
        return match.value
    return None


def normalize_period(question):
    raw_text = question.lower()

    iso_match = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", raw_text)
    if iso_match:
        return "date:{year}-{month:02d}-{day:02d}".format(
            year=int(iso_match.group(1)),
            month=int(iso_match.group(2)),
            day=int(iso_match.group(3)),
        )

    slash_match = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", raw_text)
    if slash_match:
        return "date:{year}-{month:02d}-{day:02d}".format(
            year=int(slash_match.group(3)),
            month=int(slash_match.group(2)),
            day=int(slash_match.group(1)),
        )

    month_date_match = re.search(
        rf"\b({MONTH_PATTERN})\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:\s+(\d{{4}}))?\b",
        raw_text,
    )
    if month_date_match:
        year = int(month_date_match.group(3) or date.today().year)
        month = MONTH_ALIASES[month_date_match.group(1)]
        day = int(month_date_match.group(2))
        return f"date:{year}-{month:02d}-{day:02d}"

    text = re.sub(r"[^a-z0-9\s]", " ", raw_text)
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


def extract_top_limit(question, default=5, maximum=50):
    text = question.lower()
    patterns = (
        r"\btop\s+(\d{1,3})\b",
        r"\b(\d{1,3})\s+(?:top|biggest|largest|highest)\b",
        r"\b(?:top|biggest|largest|highest)\s+expenses?\s+(\d{1,3})\b",
    )

    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue

        limit = int(match.group(1))
        if limit < 1:
            return default
        return min(limit, maximum)

    return default


def _pdf_requested(question):
    text = _normalized_text(question)
    return "pdf" in text or "print" in text


def sales_total(period="all_time", filters=None):
    transection_total = 0
    transection_rows = []
    if _include_transaction_rows(filters):
        date_sql, params = _date_filter(period)
        filter_sql, filter_params = _dimension_filter(filters)
        params.update(filter_params)
        row = _fetch_one(
            f'''
            SELECT COALESCE(SUM(t."Amount"), 0) AS total_sales
            FROM {_table_ref()} t
            {_transaction_category_link_join("t")}
            WHERE COALESCE(t.__nc_deleted, false) = false
              AND t."Income_Expense" = 'Income'
              AND {_canonical_transection_income_condition("t")}
              {filter_sql}
              {date_sql}
            ''',
            params,
        )
        transection_total = int(row["total_sales"] or 0)
        transection_rows = list_transactions(period, filters, limit=10).get("transactions") or []
    farm_summary = _farm_sales_summary(period, filters)
    sotephwar_summary = _sotephwar_income_summary(period, filters)
    farm_total = farm_summary["total_amount"]
    sotephwar_total = sotephwar_summary["total_amount"]
    total_sales = transection_total + farm_total + sotephwar_total
    amount_received = transection_total + farm_summary["amount_received"] + sotephwar_summary["amount_received"]
    outstanding_amount = farm_summary["outstanding_amount"] + sotephwar_summary["outstanding_amount"]
    return _with_filters({
        "formula": "sales_total",
        "period": period,
        "total_sales": total_sales,
        "amount_received": amount_received,
        "outstanding_amount": outstanding_amount,
        "transection_income_rows": [
            {
                "Date": row.get("Date") or row.get("invoice_date") or row.get("date") or "",
                "item": row.get("item") or row.get("category") or "-",
                "amount": int(row.get("amount") or 0),
                "payment_method": row.get("payment_method") or "-",
            }
            for row in transection_rows
        ],
        "sources": {
            "transection_income": transection_total,
            "sotephwar_transection_total_amount": sotephwar_total,
            "sotephwar_transection_total_received": sotephwar_summary["amount_received"],
            "sotephwar_transection_outstanding_balance": sotephwar_summary["outstanding_amount"],
            "farm_transection_total_amount": farm_total,
            "farm_transection_total_received": farm_summary["amount_received"],
            "farm_transection_outstanding_balance": farm_summary["outstanding_amount"],
        },
    }, filters)


def expense_total(period="all_time", filters=None):
    date_sql, params = _date_filter(period)
    filter_sql, filter_params = _dimension_filter(filters)
    params.update(filter_params)
    row = _fetch_one(
        f'''
        SELECT
          COALESCE(SUM(t."Amount"), 0) AS total_expense,
          COUNT(*) AS expense_count,
          COUNT(*) FILTER (WHERE t."Amount" IS NULL) AS missing_amount_count
        FROM {_table_ref()} t
        {_transaction_category_link_join("t")}
        WHERE COALESCE(t.__nc_deleted, false) = false
          AND t."Income_Expense" = 'Expense'
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
    income = 0
    expense = 0
    if _include_transaction_rows(filters):
        date_sql, params = _date_filter(period)
        filter_sql, filter_params = _dimension_filter(filters)
        params.update(filter_params)
        row = _fetch_one(
            f'''
            SELECT
              COALESCE(SUM(
                CASE
                  WHEN t."Income_Expense" = 'Income'
                       AND {_canonical_transection_income_condition("t")}
                    THEN t."Amount"
                  ELSE 0
                END
              ), 0) AS income,
              COALESCE(SUM(CASE WHEN t."Income_Expense" = 'Expense' THEN t."Amount" ELSE 0 END), 0) AS expense
            FROM {_table_ref()} t
            {_transaction_category_link_join("t")}
            WHERE COALESCE(t.__nc_deleted, false) = false
              {filter_sql}
              {date_sql}
            ''',
            params,
        )
        income = int(row["income"] or 0)
        expense = int(row["expense"] or 0)
    farm_summary = _farm_sales_summary(period, filters)
    sotephwar_summary = _sotephwar_income_summary(period, filters)
    farm_income = farm_summary["total_amount"]
    sotephwar_income = sotephwar_summary["total_amount"]
    income += farm_income + sotephwar_income
    return _with_filters({
        "formula": "gross_profit",
        "period": period,
        "income": income,
        "expense": expense,
        "gross_profit": income - expense,
        "sources": {
            "sotephwar_transection_total_amount": sotephwar_income,
            "farm_transection_total_amount": farm_income,
        },
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
        "sources": totals.get("sources") or {},
    }, filters)


def cash_flow(period="all_time", filters=None):
    rows = []
    if _include_transaction_rows(filters):
        date_sql, params = _date_filter(period)
        filter_sql, filter_params = _dimension_filter(filters)
        params.update(filter_params)
        rows = _fetch_all(
            f'''
            SELECT
              COALESCE(t."Payment_Method", 'Unknown') AS payment_method,
              COALESCE(SUM(
                CASE
                  WHEN t."Income_Expense" = 'Income'
                       AND {_canonical_transection_income_condition("t")}
                    THEN t."Amount"
                  ELSE 0
                END
              ), 0) AS inflow,
              COALESCE(SUM(CASE WHEN t."Income_Expense" = 'Expense' THEN t."Amount" ELSE 0 END), 0) AS outflow
            FROM {_table_ref()} t
            {_transaction_category_link_join("t")}
            WHERE COALESCE(t.__nc_deleted, false) = false
              {filter_sql}
              {date_sql}
            GROUP BY COALESCE(t."Payment_Method", 'Unknown')
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

    sotephwar_received = _sotephwar_income_summary(period, filters)["amount_received"]
    if sotephwar_received:
        total_inflow += sotephwar_received
        methods.append({
            "payment_method": "Sotephwar_Transection received",
            "inflow": sotephwar_received,
            "outflow": 0,
            "net_cash_flow": sotephwar_received,
        })

    farm_received = _farm_cash_flow(period, filters)
    if farm_received:
        total_inflow += farm_received
        methods.append({
            "payment_method": "Farm_Transection received",
            "inflow": farm_received,
            "outflow": 0,
            "net_cash_flow": farm_received,
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
    rows = []
    if _include_transaction_rows(filters):
        date_sql, params = _date_filter(period)
        filter_sql, filter_params = _dimension_filter(filters)
        params.update(filter_params)
        rows = _fetch_all(
            f'''
            SELECT
              COALESCE(t."Sector", 'Unknown') AS sector,
              COALESCE(SUM(
                CASE
                  WHEN t."Income_Expense" = 'Income'
                       AND {_canonical_transection_income_condition("t")}
                    THEN t."Amount"
                  ELSE 0
                END
              ), 0) AS income,
              COALESCE(SUM(CASE WHEN t."Income_Expense" = 'Expense' THEN t."Amount" ELSE 0 END), 0) AS expense
            FROM {_table_ref()} t
            {_transaction_category_link_join("t")}
            WHERE COALESCE(t.__nc_deleted, false) = false
              {filter_sql}
              {date_sql}
            GROUP BY COALESCE(t."Sector", 'Unknown')
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

    sotephwar_income = _sotephwar_income_summary(period, filters)["total_amount"]
    if sotephwar_income:
        for row in sectors:
            if row["sector"] == "Sote Phwar":
                row["income"] += sotephwar_income
                row["profit"] += sotephwar_income
                break
        else:
            sectors.append({
                "sector": "Sote Phwar",
                "income": sotephwar_income,
                "expense": 0,
                "profit": sotephwar_income,
            })

    farm_income = _farm_sales_total(period, filters)
    if farm_income:
        for row in sectors:
            if row["sector"] == "Farm":
                row["income"] += farm_income
                row["profit"] += farm_income
                break
        else:
            sectors.append({
                "sector": "Farm",
                "income": farm_income,
                "expense": 0,
                "profit": farm_income,
            })

    return _with_filters({
        "formula": "sector_summary",
        "period": period,
        "sectors": sectors,
    }, filters)


def category_summary(period="all_time", filters=None):
    rows = []
    if _include_transaction_rows(filters):
        date_sql, params = _date_filter(period)
        filter_sql, filter_params = _dimension_filter(filters)
        params.update(filter_params)
        category_expr = _linked_category_expr("t")
        rows = _fetch_all(
            f'''
            SELECT
              COALESCE(t."Sector", 'Unknown') AS sector,
              COALESCE({category_expr}, 'Unknown') AS category,
              COALESCE(SUM(
                CASE
                  WHEN t."Income_Expense" = 'Income'
                       AND {_canonical_transection_income_condition("t")}
                    THEN t."Amount"
                  ELSE 0
                END
              ), 0) AS income,
              COALESCE(SUM(CASE WHEN t."Income_Expense" = 'Expense' THEN t."Amount" ELSE 0 END), 0) AS expense,
              COUNT(*) AS transaction_count
            FROM {_table_ref()} t
            {_transaction_category_link_join("t")}
            WHERE COALESCE(t.__nc_deleted, false) = false
              {filter_sql}
              {date_sql}
            GROUP BY COALESCE(t."Sector", 'Unknown'), COALESCE({category_expr}, 'Unknown')
            ORDER BY sector, expense DESC, income DESC, category
            ''',
            params,
        )

    categories = []
    total_income = 0
    total_expense = 0
    total_transactions = 0
    for row in rows:
        income = int(row["income"] or 0)
        expense = int(row["expense"] or 0)
        transaction_count = int(row["transaction_count"] or 0)
        total_income += income
        total_expense += expense
        total_transactions += transaction_count
        categories.append({
            "sector": row["sector"],
            "category": row["category"],
            "income": income,
            "expense": expense,
            "net": income - expense,
            "transaction_count": transaction_count,
        })

    sotephwar_summary = _sotephwar_income_summary(period, filters)
    sotephwar_income = sotephwar_summary["total_amount"]
    sotephwar_received = sotephwar_summary["amount_received"]
    sotephwar_outstanding = sotephwar_summary["outstanding_amount"]
    if sotephwar_income:
        total_income += sotephwar_income
        total_transactions += 1
        for row in categories:
            if row["sector"] == "Sote Phwar" and row["category"] == "Sote Phwar Sales":
                row["income"] += sotephwar_income
                row["net"] += sotephwar_income
                row["transaction_count"] += 1
                row["amount_received"] = int(row.get("amount_received") or 0) + sotephwar_received
                row["outstanding_amount"] = int(row.get("outstanding_amount") or 0) + sotephwar_outstanding
                break
        else:
            categories.append({
                "sector": "Sote Phwar",
                "category": "Sote Phwar Sales",
                "income": sotephwar_income,
                "expense": 0,
                "net": sotephwar_income,
                "transaction_count": 1,
                "amount_received": sotephwar_received,
                "outstanding_amount": sotephwar_outstanding,
            })

    farm_rows = _farm_sales_rows(period, filters, limit=None)
    if farm_rows:
        show_farm_customers = (
            (filters or {}).get("sector") == "Farm"
            and (filters or {}).get("income_expense") == "Income"
        )
        farm_income = sum(row["total_amount"] for row in farm_rows)
        farm_count = sum(row["invoice_count"] for row in farm_rows)
        total_income += farm_income
        total_transactions += farm_count
        if show_farm_customers:
            for row in farm_rows:
                categories.append({
                    "sector": "Farm",
                    "category": row["item"] or "Farm Sales",
                    "customer_name": row.get("customer_name") or row["item"] or "",
                    "income": row["total_amount"],
                    "expense": 0,
                    "net": row["total_amount"],
                    "transaction_count": row["invoice_count"],
                    "amount_received": row["amount_received"],
                    "outstanding_amount": row["outstanding_amount"],
                })
        else:
            for row in categories:
                if row["sector"] == "Farm" and row["category"] == "Farm Sales":
                    row["income"] += farm_income
                    row["net"] += farm_income
                    row["transaction_count"] += farm_count
                    row["amount_received"] = int(row.get("amount_received") or 0) + sum(farm_row["amount_received"] for farm_row in farm_rows)
                    row["outstanding_amount"] = int(row.get("outstanding_amount") or 0) + sum(farm_row["outstanding_amount"] for farm_row in farm_rows)
                    break
            else:
                categories.append({
                    "sector": "Farm",
                    "category": "Farm Sales",
                    "income": farm_income,
                    "expense": 0,
                    "net": farm_income,
                    "transaction_count": farm_count,
                    "amount_received": sum(row["amount_received"] for row in farm_rows),
                    "outstanding_amount": sum(row["outstanding_amount"] for row in farm_rows),
                })

    categories.sort(
        key=lambda row: (
            row.get("income", 0),
            row.get("expense", 0),
            row.get("transaction_count", 0),
        ),
        reverse=True,
    )

    return _with_filters({
        "formula": "category_summary",
        "period": period,
        "total_income": total_income,
        "total_expense": total_expense,
        "net_total": total_income - total_expense,
        "transaction_count": total_transactions,
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
          t."Date",
          COALESCE(t."Sector", 'Unknown') AS sector,
          COALESCE({_linked_category_expr("t")}, 'Unknown') AS category,
          COALESCE(t."Item_Description", '') AS item,
          t."Amount" AS amount,
          COALESCE(t."Payment_Method", 'Unknown') AS payment_method
        FROM {_table_ref()} t
        {_transaction_category_link_join("t")}
        WHERE COALESCE(t.__nc_deleted, false) = false
          AND t."Income_Expense" = 'Expense'
          AND t."Amount" IS NOT NULL
          {filter_sql}
          {date_sql}
        ORDER BY "Amount" DESC NULLS LAST
        LIMIT %(limit)s
        ''',
        params,
    )

    for row in rows:
        row["amount"] = int(row["amount"] or 0)

    return _with_filters({
        "formula": "top_expenses",
        "period": period,
        "expenses": rows,
    }, filters)


def top_income(period="all_time", filters=None, limit=5):
    rows = []
    if _include_transaction_rows(filters):
        date_sql, params = _date_filter(period)
        filter_sql, filter_params = _dimension_filter(filters)
        params.update(filter_params)
        params["limit"] = limit
        rows = _fetch_all(
            f'''
            SELECT
              COALESCE(t."Sector", 'Unknown') AS sector,
              COALESCE({_linked_category_expr("t")}, 'Unknown') AS category,
              COALESCE(NULLIF(TRIM(t."Item_Description"), ''), COALESCE({_linked_category_expr("t")}, 'Unknown')) AS item,
              COALESCE(SUM(t."Amount"), 0) AS amount,
              COALESCE(SUM(t."Amount"), 0) AS total_amount,
              COALESCE(SUM(t."Amount"), 0) AS amount_received,
              0 AS outstanding_amount,
              COUNT(*) AS invoice_count,
              COALESCE(t."Payment_Method", 'Unknown') AS payment_method
            FROM {_table_ref()} t
            {_transaction_category_link_join("t")}
            WHERE COALESCE(t.__nc_deleted, false) = false
              AND t."Income_Expense" = 'Income'
              AND {_canonical_transection_income_condition("t")}
              AND t."Amount" IS NOT NULL
              {filter_sql}
              {date_sql}
            GROUP BY
              COALESCE(t."Sector", 'Unknown'),
              COALESCE({_linked_category_expr("t")}, 'Unknown'),
              COALESCE(NULLIF(TRIM(t."Item_Description"), ''), COALESCE({_linked_category_expr("t")}, 'Unknown')),
              COALESCE(t."Payment_Method", 'Unknown')
            ORDER BY amount DESC NULLS LAST
            LIMIT %(limit)s
            ''',
            params,
        )

    for row in rows:
        row["amount"] = int(row["amount"] or 0)
        row["total_amount"] = int(row.get("total_amount") or row["amount"])
        row["amount_received"] = int(row.get("amount_received") or 0)
        row["outstanding_amount"] = int(row.get("outstanding_amount") or 0)
        row["invoice_count"] = int(row.get("invoice_count") or 0)

    rows = sorted(
        rows
        + _sotephwar_income_rows(period, filters, limit=limit)
        + _farm_sales_rows(period, filters, limit=limit),
        key=lambda row: row.get("amount") or 0,
        reverse=True,
    )[:limit]

    return _with_filters({
        "formula": "top_income",
        "period": period,
        "income": rows,
    }, filters)


def list_transactions(period="all_time", filters=None, limit=20):
    date_sql, params = _date_filter(period)
    filter_sql, filter_params = _dimension_filter(filters)
    params.update(filter_params)
    params["limit"] = limit
    note_select = ',\n          COALESCE("Note", \'\') AS note' if _transaction_column_exists("Note") else ""
    rows = _fetch_all(
        f'''
        SELECT
          t.id,
          t."Date",
          COALESCE(t."Income_Expense", '') AS income_expense,
          COALESCE(t."Sector", 'Unknown') AS sector,
          COALESCE({_linked_category_expr("t")}, 'Unknown') AS category,
          COALESCE(t."Item_Description", '') AS item,
          t."Amount" AS amount,
          COALESCE(t."Payment_Method", 'Unknown') AS payment_method
          {note_select}
        FROM {_table_ref()} t
        {_transaction_category_link_join("t")}
        WHERE COALESCE(t.__nc_deleted, false) = false
          {filter_sql}
          {date_sql}
        ORDER BY t."Date" DESC NULLS LAST, t.id DESC
        LIMIT %(limit)s
        ''',
        params,
    )

    for row in rows:
        row["amount"] = int(row["amount"] or 0)

    return _with_filters({
        "formula": "list_transactions",
        "period": period,
        "transactions": rows,
    }, filters)


def sotephwar_transection_summary(period="all_time", include_customers=True):
    date_sql, params = _date_filter_for_column(period, '"Invoice_Date"')
    row = _fetch_one(
        f'''
        SELECT
          COUNT(*) AS invoice_count,
          COALESCE(SUM("Total_Amount"), 0) AS total_amount,
          COALESCE(SUM("Total_Received"), 0) AS amount_received,
          COALESCE(SUM("Outstanding_Balance"), 0) AS outstanding_amount
        FROM {_sotephwar_transection_table_ref()}
        WHERE COALESCE(__nc_deleted, false) = false
          {date_sql}
        ''',
        params,
    )

    result = {
        "formula": "sotephwar_transection_summary",
        "period": period,
        "invoice_count": int(row["invoice_count"] or 0),
        "total_amount": int(row["total_amount"] or 0),
        "amount_received": int(row["amount_received"] or 0),
        "outstanding_amount": int(row["outstanding_amount"] or 0),
    }
    if include_customers:
        result["customers"] = _sotephwar_income_rows(period, None, limit=None)
    return result


def sotephwar_transection_monthly_summary(period="this_year"):
    date_sql, params = _date_filter_for_column(period, '"Invoice_Date"')
    rows = _fetch_all(
        f'''
        SELECT
          TO_CHAR(DATE_TRUNC('month', "Invoice_Date"), 'YYYY-MM') AS month,
          COUNT(*) AS invoice_count,
          COALESCE(SUM("Total_Amount"), 0) AS total_amount,
          COALESCE(SUM("Total_Received"), 0) AS amount_received,
          COALESCE(SUM("Outstanding_Balance"), 0) AS outstanding_amount
        FROM {_sotephwar_transection_table_ref()}
        WHERE COALESCE(__nc_deleted, false) = false
          AND "Invoice_Date" IS NOT NULL
          {date_sql}
        GROUP BY DATE_TRUNC('month', "Invoice_Date")
        ORDER BY DATE_TRUNC('month', "Invoice_Date")
        ''',
        params,
    )

    for row in rows:
        row["invoice_count"] = int(row["invoice_count"] or 0)
        row["total_amount"] = int(row["total_amount"] or 0)
        row["amount_received"] = int(row["amount_received"] or 0)
        row["outstanding_amount"] = int(row["outstanding_amount"] or 0)

    return {
        "formula": "sotephwar_transection_monthly_summary",
        "period": period,
        "months": rows,
    }


def sotephwar_transection_top(period="all_time", limit=5):
    date_sql, params = _date_filter_for_column(period, '"Invoice_Date"')
    params["limit"] = limit
    rows = _fetch_all(
        f'''
        SELECT
          s."Invoice_Date" AS invoice_date,
          COALESCE(s."Invoice_Number", '') AS invoice_number,
          COALESCE({_linked_customer_expr("s")}, '') AS customer_name,
          COALESCE(s."Item", '') AS item,
          COALESCE(s."Note", '') AS note,
          s."Quantity" AS quantity,
          s."Total_Amount" AS total_amount,
          s."Total_Received" AS amount_received,
          COALESCE(s."Outstanding_Balance", 0) AS outstanding_amount
        FROM {_sotephwar_transection_table_ref()} s
        {_sotephwar_customer_link_join("s")}
        WHERE COALESCE(s.__nc_deleted, false) = false
          AND s."Total_Amount" IS NOT NULL
          {date_sql}
        ORDER BY s."Total_Amount" DESC NULLS LAST
        LIMIT %(limit)s
        ''',
        params,
    )

    for row in rows:
        row["quantity"] = int(row["quantity"] or 0)
        row["total_amount"] = int(row["total_amount"] or 0)
        row["amount_received"] = int(row["amount_received"] or 0)
        row["outstanding_amount"] = int(row["outstanding_amount"] or 0)

    return {
        "formula": "sotephwar_transection_top",
        "period": period,
        "invoices": rows,
    }


def sotephwar_transection_list(period="all_time", limit=20, unpaid_only=False):
    date_sql, params = _date_filter_for_column(period, '"Invoice_Date"')
    params["limit"] = limit
    unpaid_sql = ""
    if unpaid_only:
        unpaid_sql = 'AND COALESCE("Outstanding_Balance", 0) > 0'

    rows = _fetch_all(
        f'''
        SELECT
          s."Invoice_Date" AS invoice_date,
          COALESCE(s."Invoice_Number", '') AS invoice_number,
          COALESCE({_linked_customer_expr("s")}, '') AS customer_name,
          COALESCE(s."Item", '') AS item,
          COALESCE(s."Note", '') AS note,
          s."Quantity" AS quantity,
          s."Total_Amount" AS total_amount,
          s."Total_Received" AS amount_received,
          COALESCE(s."Outstanding_Balance", 0) AS outstanding_amount
        FROM {_sotephwar_transection_table_ref()} s
        {_sotephwar_customer_link_join("s")}
        WHERE COALESCE(s.__nc_deleted, false) = false
          {unpaid_sql}
          {date_sql}
        ORDER BY s."Invoice_Date" DESC NULLS LAST, s.id DESC
        LIMIT %(limit)s
        ''',
        params,
    )

    for row in rows:
        row["quantity"] = int(row["quantity"] or 0)
        row["total_amount"] = int(row["total_amount"] or 0)
        row["amount_received"] = int(row["amount_received"] or 0)
        row["outstanding_amount"] = int(row["outstanding_amount"] or 0)

    return {
        "formula": "sotephwar_transection_list",
        "period": period,
        "unpaid_only": unpaid_only,
        "invoices": rows,
    }


def sotephwar_transection_quantity(period="all_time", item=None):
    date_sql, params = _date_filter_for_column(period, '"Invoice_Date"')
    item_sql = ""
    if item:
        item_sql = 'AND "Item" = %(item)s'
        params["item"] = item

    row = _fetch_one(
        f'''
        SELECT
          COALESCE("Item", 'All items') AS item,
          COUNT(*) AS invoice_count,
          COALESCE(SUM("Quantity"), 0) AS quantity,
          COALESCE(SUM("Total_Amount"), 0) AS total_amount,
          COALESCE(SUM("Total_Received"), 0) AS amount_received,
          COALESCE(SUM("Outstanding_Balance"), 0) AS outstanding_amount
        FROM {_sotephwar_transection_table_ref()}
        WHERE COALESCE(__nc_deleted, false) = false
          {item_sql}
          {date_sql}
        GROUP BY COALESCE("Item", 'All items')
        ORDER BY quantity DESC
        LIMIT 1
        ''',
        params,
    )

    return {
        "formula": "sotephwar_transection_quantity",
        "period": period,
        "item": item or (row.get("item") if row else "All items"),
        "invoice_count": int(row.get("invoice_count") or 0),
        "quantity": int(row.get("quantity") or 0),
        "total_amount": int(row.get("total_amount") or 0),
        "amount_received": int(row.get("amount_received") or 0),
        "outstanding_amount": int(row.get("outstanding_amount") or 0),
    }


def sotephwar_transection_customer(
    period="all_time",
    customer=None,
    limit=50,
    unpaid_only=False,
    invoice_numbers=None,
    include_note=False,
):
    date_sql, params = _date_filter_for_column(period, '"Invoice_Date"')
    params["limit"] = limit
    customer_sql = ""
    if customer:
        customer_sql = f"AND {_customer_normalized_sql()} = %(customer_normalized)s"
        params["customer_normalized"] = normalize_name(customer)
    unpaid_sql = ""
    if unpaid_only:
        unpaid_sql = 'AND COALESCE("Outstanding_Balance", 0) > 0'
    invoice_sql = ""
    if invoice_numbers:
        invoice_sql = 'AND "Invoice_Number"::text = ANY(%(invoice_numbers)s)'
        params["invoice_numbers"] = invoice_numbers

    rows = _fetch_all(
        f'''
        SELECT
          s."Invoice_Date" AS invoice_date,
          COALESCE(s."Invoice_Number", '') AS invoice_number,
          COALESCE({_linked_customer_expr("s")}, '') AS customer_name,
          COALESCE(s."Item", '') AS item,
          COALESCE(s."Note", '') AS note,
          s."Quantity" AS quantity,
          s."Total_Amount" AS total_amount,
          s."Total_Received" AS amount_received,
          COALESCE(s."Outstanding_Balance", 0) AS outstanding_amount
        FROM {_sotephwar_transection_table_ref()} s
        {_sotephwar_customer_link_join("s")}
        WHERE COALESCE(s.__nc_deleted, false) = false
          {customer_sql}
          {unpaid_sql}
          {invoice_sql}
          {date_sql}
        ORDER BY customer_name, s."Invoice_Date", s.id
        LIMIT %(limit)s
        ''',
        params,
    )

    for row in rows:
        row["quantity"] = int(row["quantity"] or 0)
        row["total_amount"] = int(row["total_amount"] or 0)
        row["amount_received"] = int(row["amount_received"] or 0)
        row["outstanding_amount"] = int(row["outstanding_amount"] or 0)

    return {
        "formula": "sotephwar_transection_customer",
        "period": period,
        "customer": customer,
        "unpaid_only": unpaid_only,
        "invoice_numbers": invoice_numbers or [],
        "include_note": include_note,
        "invoices": rows,
    }


def sotephwar_payment_update(question):
    values = _parse_sotephwar_payment_update(question)
    missing = []
    if not values.get("invoice_number"):
        missing.append("voucher number")
    if not values.get("amount"):
        missing.append("received amount")
    if missing:
        return {
            "formula": "sotephwar_payment_update",
            "period": "all_time",
            "updated": False,
            "missing": missing,
            "values": values,
        }

    note = "Received {date}: {amount:,} kyats".format(
        date=values["received_date"].isoformat(),
        amount=values["amount"],
    )
    try:
        saved = save_payment_receive(
            sector="Sote Phwar",
            voucher_number=values["invoice_number"],
            receive_amount=values["amount"],
            payment_method="Sote Phwar Receive",
            notes=note,
            recorded_by="Business AI",
            receive_date=values["received_date"],
        )
    except LookupError:
        return {
            "formula": "sotephwar_payment_update",
            "period": "all_time",
            "updated": False,
            "missing": ["matching voucher"],
            "invoice_number": values["invoice_number"],
            "payment_amount": values["amount"],
            "received_date": values["received_date"].isoformat(),
            "invoices": [],
        }
    except ValueError as exc:
        return {
            "formula": "sotephwar_payment_update",
            "period": "all_time",
            "updated": False,
            "error": str(exc),
            "invoice_number": values["invoice_number"],
            "payment_amount": values["amount"],
            "received_date": values["received_date"].isoformat(),
            "invoices": [],
        }

    previous_received = int(saved["payment"].get("previous_paid") or 0)
    rows = sotephwar_transection_customer(
        period="all_time",
        invoice_numbers=[values["invoice_number"]],
        limit=50,
        include_note=True,
    ).get("invoices") or []

    for row in rows:
        row["quantity"] = int(row["quantity"] or 0)
        row["total_amount"] = int(row["total_amount"] or 0)
        row["previous_amount_received"] = previous_received
        row["amount_received"] = int(row["amount_received"] or 0)
        row["outstanding_amount"] = int(row["outstanding_amount"] or 0)

    return {
        "formula": "sotephwar_payment_update",
        "period": "all_time",
        "updated": bool(rows),
        "missing": [] if rows else ["matching voucher"],
        "invoice_number": values["invoice_number"],
        "payment_amount": values["amount"],
        "received_date": values["received_date"].isoformat(),
        "invoices": rows,
    }


def sotephwar_inventory_stock(period="all_time", product=None, store=None):
    product_sql = ""
    store_sql = ""
    params = {}
    if product:
        product_sql = "AND product = %(product)s"
        params["product"] = product
    if store:
        store_sql = "AND store = %(store)s"
        params["store"] = store
    to_store = _sotephwar_inventory_store_expr('"To_Store"')
    from_store = _sotephwar_inventory_store_expr('"From_Store"')

    rows = _fetch_all(
        f'''
        WITH movements AS (
          SELECT
            {to_store} AS store,
            "Product" AS product,
            COALESCE("Qty", 0) AS qty
          FROM {_sotephwar_inventory_table_ref()}
          WHERE COALESCE("__nc_deleted", false) = false
            AND "To_Store" IS NOT NULL
            AND "To_Store" NOT IN ('-', 'Customer')
          UNION ALL
          SELECT
            {from_store} AS store,
            "Product" AS product,
            -COALESCE("Qty", 0) AS qty
          FROM {_sotephwar_inventory_table_ref()}
          WHERE COALESCE("__nc_deleted", false) = false
            AND "From_Store" IS NOT NULL
            AND "From_Store" NOT IN ('-', 'Customer')
        )
        SELECT store, product, COALESCE(SUM(qty), 0) AS stock_qty
        FROM movements
        WHERE 1 = 1
          {product_sql}
          {store_sql}
        GROUP BY store, product
        HAVING COALESCE(SUM(qty), 0) <> 0
        ORDER BY store, product
        ''',
        params,
    )
    for row in rows:
        row["stock_qty"] = int(row["stock_qty"] or 0)
    return {
        "formula": "sotephwar_inventory_stock",
        "period": "all_time",
        "product": product,
        "store": store,
        "stock": rows,
    }


def sotephwar_inventory_movement_summary(period="all_time", product=None, store=None, movement_type=None):
    date_sql, params = _date_filter(period)
    product_sql = ""
    store_sql = ""
    type_sql = ""
    if product:
        product_sql = 'AND "Product" = %(product)s'
        params["product"] = product
    if store:
        store_sql = 'AND ("From_Store" = ANY(%(store_values)s) OR "To_Store" = ANY(%(store_values)s))'
        params["store_values"] = _sotephwar_inventory_store_values(store)
    if movement_type:
        type_sql = 'AND "Type" = %(movement_type)s'
        params["movement_type"] = movement_type

    rows = _fetch_all(
        f'''
        SELECT
          COALESCE("Type", '') AS type,
          COALESCE("Product", '') AS product,
          COALESCE(SUM("Qty"), 0) AS quantity,
          COUNT(*) AS movement_count
        FROM {_sotephwar_inventory_table_ref()}
        WHERE COALESCE("__nc_deleted", false) = false
          {date_sql}
          {product_sql}
          {store_sql}
          {type_sql}
        GROUP BY "Type", "Product"
        ORDER BY "Type", "Product"
        ''',
        params,
    )
    for row in rows:
        row["quantity"] = int(row["quantity"] or 0)
        row["movement_count"] = int(row["movement_count"] or 0)
    return {
        "formula": "sotephwar_inventory_movement_summary",
        "period": period,
        "product": product,
        "store": store,
        "movement_type": movement_type,
        "movements": rows,
    }


def sotephwar_inventory_list(period="all_time", product=None, store=None, movement_type=None, limit=20):
    date_sql, params = _date_filter(period)
    product_sql = ""
    store_sql = ""
    type_sql = ""
    if product:
        product_sql = 'AND "Product" = %(product)s'
        params["product"] = product
    if store:
        store_sql = 'AND ("From_Store" = ANY(%(store_values)s) OR "To_Store" = ANY(%(store_values)s))'
        params["store_values"] = _sotephwar_inventory_store_values(store)
    if movement_type:
        type_sql = 'AND "Type" = %(movement_type)s'
        params["movement_type"] = movement_type
    params["limit"] = limit

    rows = _fetch_all(
        f'''
        SELECT
          id,
          "Date" AS date,
          COALESCE("Type", '') AS type,
          COALESCE("From_Store", '') AS from_store,
          COALESCE("To_Store", '') AS to_store,
          COALESCE("Product", '') AS product,
          COALESCE("Qty", 0) AS quantity,
          COALESCE("Note", '') AS note
        FROM {_sotephwar_inventory_table_ref()}
        WHERE COALESCE("__nc_deleted", false) = false
          {date_sql}
          {product_sql}
          {store_sql}
          {type_sql}
        ORDER BY "Date" DESC NULLS LAST, id DESC
        LIMIT %(limit)s
        ''',
        params,
    )
    for row in rows:
        row["quantity"] = int(row["quantity"] or 0)
    return {
        "formula": "sotephwar_inventory_list",
        "period": period,
        "product": product,
        "store": store,
        "movement_type": movement_type,
        "movements": rows,
    }


def financial_obligation_summary(status=None, category=None):
    status_sql = ""
    category_sql = ""
    params = {}
    if status:
        status_sql = 'AND "Status" ILIKE %(status)s'
        params["status"] = status
    if category:
        category_sql = 'AND "Category" ILIKE %(category)s'
        params["category"] = f"%{category}%"

    rows = _fetch_all(
        f'''
        SELECT
          COALESCE("Category", '') AS category,
          COALESCE("Status", '') AS status,
          COALESCE(SUM("Amount"), 0) AS amount,
          COUNT(*) AS obligation_count,
          MIN("Next_Due_Date") AS next_due_date
        FROM {_financial_obligations_table_ref()}
        WHERE COALESCE("__nc_deleted", false) = false
          {status_sql}
          {category_sql}
        GROUP BY "Category", "Status"
        ORDER BY "Category", "Status"
        ''',
        params,
    )
    for row in rows:
        row["amount"] = int(row["amount"] or 0)
        row["obligation_count"] = int(row["obligation_count"] or 0)
    return {
        "formula": "financial_obligation_summary",
        "period": "all_time",
        "status": status,
        "category": category,
        "summary": rows,
    }


def financial_obligation_due(days=30, status="Active", category=None, limit=20):
    today = date.today()
    end_date = today + timedelta(days=days)
    params = {
        "today": today,
        "end_date": end_date,
        "limit": limit,
    }
    status_sql = ""
    category_sql = ""
    if status:
        status_sql = 'AND "Status" ILIKE %(status)s'
        params["status"] = status
    if category:
        category_sql = 'AND "Category" ILIKE %(category)s'
        params["category"] = f"%{category}%"

    rows = _fetch_all(
        f'''
        SELECT
          id,
          COALESCE("Category", '') AS category,
          COALESCE("Subcategory", '') AS subcategory,
          COALESCE("Creditor", '') AS creditor,
          COALESCE("Amount", 0) AS amount,
          COALESCE("Frequency", '') AS frequency,
          "Start_Date" AS start_date,
          "Next_Due_Date" AS next_due_date,
          COALESCE("Status", '') AS status,
          COALESCE("Notes", '') AS notes
        FROM {_financial_obligations_table_ref()}
        WHERE COALESCE("__nc_deleted", false) = false
          AND "Next_Due_Date" IS NOT NULL
          AND "Next_Due_Date" <= %(end_date)s
          {status_sql}
          {category_sql}
        ORDER BY "Next_Due_Date", id
        LIMIT %(limit)s
        ''',
        params,
    )
    for row in rows:
        row["amount"] = int(row["amount"] or 0)
        due_date = row.get("next_due_date")
        row["days_until_due"] = (due_date - today).days if due_date else None
    return {
        "formula": "financial_obligation_due",
        "period": "all_time",
        "days": days,
        "status": status,
        "category": category,
        "obligations": rows,
    }


def financial_obligation_list(status=None, category=None, creditor=None, limit=20):
    params = {"limit": limit}
    status_sql = ""
    category_sql = ""
    creditor_sql = ""
    if status:
        status_sql = 'AND "Status" ILIKE %(status)s'
        params["status"] = status
    if category:
        category_sql = 'AND "Category" ILIKE %(category)s'
        params["category"] = f"%{category}%"
    if creditor:
        creditor_sql = 'AND "Creditor" ILIKE %(creditor)s'
        params["creditor"] = f"%{creditor}%"

    rows = _fetch_all(
        f'''
        SELECT
          id,
          "Date" AS date,
          COALESCE("Category", '') AS category,
          COALESCE("Subcategory", '') AS subcategory,
          COALESCE("Creditor", '') AS creditor,
          COALESCE("Amount", 0) AS amount,
          COALESCE("Frequency", '') AS frequency,
          "Start_Date" AS start_date,
          "Next_Due_Date" AS next_due_date,
          COALESCE("Status", '') AS status,
          COALESCE("Notes", '') AS notes
        FROM {_financial_obligations_table_ref()}
        WHERE COALESCE("__nc_deleted", false) = false
          {status_sql}
          {category_sql}
          {creditor_sql}
        ORDER BY "Next_Due_Date" NULLS LAST, id
        LIMIT %(limit)s
        ''',
        params,
    )
    for row in rows:
        row["amount"] = int(row["amount"] or 0)
    return {
        "formula": "financial_obligation_list",
        "period": "all_time",
        "status": status,
        "category": category,
        "creditor": creditor,
        "obligations": rows,
    }


def financial_obligation_insert(question):
    values = _parse_financial_obligation_insert(question)
    missing = []
    if not values.get("creditor"):
        missing.append("creditor")
    if not values.get("amount"):
        missing.append("amount")
    if not values.get("next_due_date"):
        missing.append("next due date YYYY-MM-DD")
    if missing:
        return {
            "formula": "financial_obligation_insert",
            "period": "all_time",
            "inserted": False,
            "missing": missing,
            "values": values,
        }

    row = _fetch_one(
        f'''
        INSERT INTO {_financial_obligations_table_ref()}
          ("Date", "Category", "Subcategory", "Creditor", "Amount", "Frequency",
           "Start_Date", "Next_Due_Date", "Status", "Notes")
        VALUES
          (%(date)s, %(category)s, %(subcategory)s, %(creditor)s, %(amount)s, %(frequency)s,
           %(start_date)s, %(next_due_date)s, %(status)s, %(notes)s)
        RETURNING
          id,
          "Category" AS category,
          "Subcategory" AS subcategory,
          "Creditor" AS creditor,
          "Amount" AS amount,
          "Frequency" AS frequency,
          "Start_Date" AS start_date,
          "Next_Due_Date" AS next_due_date,
          "Status" AS status,
          "Notes" AS notes
        ''',
        {
            "date": date.today(),
            **values,
        },
    )
    row["amount"] = int(row.get("amount") or 0)
    return {
        "formula": "financial_obligation_insert",
        "period": "all_time",
        "inserted": True,
        "obligation": row,
    }


def ensure_payment_receive_table():
    global _PAYMENT_RECEIVE_TABLE_READY
    if _PAYMENT_RECEIVE_TABLE_READY:
        return
    with _PAYMENT_SCHEMA_LOCK:
        if _PAYMENT_RECEIVE_TABLE_READY:
            return
        if not _payment_receive_column_exists("Invoice_Date"):
            _execute(
                f'''
                CREATE TABLE IF NOT EXISTS {_payment_receive_table_ref()} (
                  id BIGSERIAL PRIMARY KEY,
                  "Receive_Date" date NOT NULL,
                  "Sector" text NOT NULL,
                  "Voucher_Number" text NOT NULL,
                  "Invoice_Date" date,
                  "Customer" text,
                  "Invoice_Amount" numeric DEFAULT 0,
                  "Previous_Paid" numeric DEFAULT 0,
                  "Receive_Amount" numeric NOT NULL,
                  "Outstanding_Balance" numeric DEFAULT 0,
                  "Payment_Method" text,
                  "Reference_Number" text,
                  "Notes" text,
                  "Recorded_By" text,
                  "Created_At" timestamptz DEFAULT now(),
                  "Updated_At" timestamptz DEFAULT now()
                )
                '''
            )
            _execute(
                f'''
                ALTER TABLE {_payment_receive_table_ref()}
                  ADD COLUMN IF NOT EXISTS "Invoice_Date" date
                '''
            )
        _PAYMENT_RECEIVE_TABLE_READY = True


def ensure_voucher_summary_fields():
    global _VOUCHER_SUMMARY_FIELDS_READY
    if _VOUCHER_SUMMARY_FIELDS_READY:
        return
    with _PAYMENT_SCHEMA_LOCK:
        if _VOUCHER_SUMMARY_FIELDS_READY:
            return
        farm_table = getattr(config, "FARM_TRANSECTION_TABLE", "farm_transection")
        sote_table = getattr(config, "SOTEPHWAR_TRANSECTION_TABLE", "Sotephwar_Transection")
        farm_ready = (
            _schema_table_column_exists(farm_table, "Total_Amount")
            and _schema_table_column_exists(farm_table, "Total_Received")
            and _schema_table_column_exists(farm_table, "Outstanding_Balance")
            and _schema_table_column_exists(farm_table, "Payment_Status")
        )
        sote_ready = (
            _schema_table_column_exists(sote_table, "Total_Received")
            and _schema_table_column_exists(sote_table, "Outstanding_Balance")
            and _schema_table_column_exists(sote_table, "Payment_Status")
        )
        if not (farm_ready and sote_ready):
            _execute(
                f'''
                ALTER TABLE {_farm_transection_table_ref()}
                  ADD COLUMN IF NOT EXISTS "Total_Amount" numeric DEFAULT 0
                '''
            )
            for table_ref in (_farm_transection_table_ref(), _sotephwar_transection_table_ref()):
                _execute(
                    f'''
                    ALTER TABLE {table_ref}
                      ADD COLUMN IF NOT EXISTS "Total_Received" numeric DEFAULT 0,
                      ADD COLUMN IF NOT EXISTS "Outstanding_Balance" numeric DEFAULT 0,
                      ADD COLUMN IF NOT EXISTS "Payment_Status" text DEFAULT 'Outstanding'
                    '''
                )
        _VOUCHER_SUMMARY_FIELDS_READY = True


def _payment_status(voucher_total, total_received):
    voucher_total = int(voucher_total or 0)
    total_received = int(total_received or 0)
    if voucher_total > 0 and total_received >= voucher_total:
        return "Paid"
    if total_received > 0:
        return "Partial"
    return "Outstanding"


def _payment_voucher_lookup(sector, voucher_number, connection=None, invoice_date=None, customer=None):
    fetch_all = _fetch_all if connection is None else lambda sql, params=None: _fetch_all_in_connection(connection, sql, params)
    params = {"voucher_number": voucher_number}
    farm_filters = []
    sote_filters = []
    if invoice_date:
        params["invoice_date"] = invoice_date
        farm_filters.append('AND f."Date" = %(invoice_date)s')
        sote_filters.append('AND s."Invoice_Date" = %(invoice_date)s')
    if customer:
        params["customer"] = customer
        farm_filters.append(f"AND COALESCE({_linked_farm_customer_expr('f')}, '') = %(customer)s")
        sote_filters.append(f"AND COALESCE({_linked_customer_expr('s')}, '') = %(customer)s")

    if sector == "Farm":
        rows = fetch_all(
            f'''
            SELECT
              'Farm' AS sector,
              COALESCE(f."Invoice_Number"::text, '') AS voucher_number,
              f."Date" AS invoice_date,
              COALESCE({_linked_farm_customer_expr("f")}, '') AS customer,
              COALESCE(SUM(f."Total_Amount"), 0) AS invoice_amount,
              COALESCE(SUM(f."Total_Received"), 0) AS current_received
            FROM {_farm_transection_table_ref()} f
            {_farm_customer_link_join("f")}
            WHERE COALESCE(f.__nc_deleted, false) = false
              AND f."Invoice_Number"::text = %(voucher_number)s
              {" ".join(farm_filters)}
            GROUP BY
              f."Invoice_Number"::text,
              f."Date",
              COALESCE({_linked_farm_customer_expr("f")}, '')
            ''',
            params,
        )
    elif sector == "Sote Phwar":
        rows = fetch_all(
            f'''
            SELECT
              'Sote Phwar' AS sector,
              COALESCE(s."Invoice_Number"::text, '') AS voucher_number,
              s."Invoice_Date" AS invoice_date,
              COALESCE({_linked_customer_expr("s")}, '') AS customer,
              COALESCE(SUM(s."Total_Amount"), 0) AS invoice_amount,
              COALESCE(SUM(s."Total_Received"), 0) AS current_received
            FROM {_sotephwar_transection_table_ref()} s
            {_sotephwar_customer_link_join("s")}
            WHERE COALESCE(s.__nc_deleted, false) = false
              AND s."Invoice_Number"::text = %(voucher_number)s
              {" ".join(sote_filters)}
            GROUP BY
              s."Invoice_Number"::text,
              s."Invoice_Date",
              COALESCE({_linked_customer_expr("s")}, '')
            ''',
            params,
        )
    else:
        return {}

    if len(rows) > 1:
        raise ValueError(
            "Multiple vouchers match this voucher number. Specify invoice date and customer."
        )
    return rows[0] if rows else {}


def _lock_payment_voucher(connection, sector, voucher_number, invoice_date=None, customer=None):
    lock_key = "|".join([
        str(sector or ""),
        str(voucher_number or ""),
        str(invoice_date or ""),
        str(customer or ""),
    ])
    _execute_in_connection(
        connection,
        "SELECT pg_advisory_xact_lock(hashtextextended(%(lock_key)s, 0))",
        {"lock_key": lock_key},
    )


def _payment_receive_total(sector, voucher_number, connection=None, invoice_date=None, customer=None):
    fetch_one = _fetch_one if connection is None else lambda sql, params=None: _fetch_one_in_connection(connection, sql, params)
    params = {"sector": sector, "voucher_number": voucher_number}
    filters = []
    if invoice_date:
        params["invoice_date"] = invoice_date
        filters.append('AND "Invoice_Date" = %(invoice_date)s')
    if customer:
        params["customer"] = customer
        filters.append('AND COALESCE("Customer", \'\') = %(customer)s')
    row = fetch_one(
        f'''
        SELECT COALESCE(SUM("Receive_Amount"), 0) AS payment_received
        FROM {_payment_receive_table_ref()}
        WHERE "Sector" = %(sector)s
          AND "Voucher_Number" = %(voucher_number)s
          {" ".join(filters)}
        ''',
        params,
    )
    return int(row.get("payment_received") or 0)


def _payment_previous_paid(sector, voucher_number):
    return _payment_receive_total(sector, voucher_number)


def _payment_balance_status(total_amount, total_received):
    total_amount = int(total_amount or 0)
    total_received = int(total_received or 0)
    outstanding_balance = total_amount - total_received
    if outstanding_balance < 0:
        return outstanding_balance, None
    if total_received <= 0:
        return outstanding_balance, "Outstanding"
    if outstanding_balance == 0:
        return outstanding_balance, "Paid"
    return outstanding_balance, "Partial"


def _update_voucher_payment_summary(
    sector,
    voucher_number,
    connection=None,
    invoice_date=None,
    customer=None,
    total_received=None,
):
    ensure_voucher_summary_fields()
    voucher = _payment_voucher_lookup(
        sector,
        voucher_number,
        connection=connection,
        invoice_date=invoice_date,
        customer=customer,
    )
    voucher_total = int(voucher.get("invoice_amount") or 0)
    if total_received is None:
        total_received = _payment_receive_total(
            sector,
            voucher_number,
            connection=connection,
            invoice_date=invoice_date,
            customer=customer,
        )
    total_received = int(total_received or 0)
    outstanding_balance, payment_status = _payment_balance_status(voucher_total, total_received)
    if outstanding_balance < 0:
        logger.error(
            "Rejecting payment summary update for %s %s: total_amount=%s total_received=%s outstanding_balance=%s",
            sector,
            voucher_number,
            voucher_total,
            total_received,
            outstanding_balance,
        )
        raise ValueError("Outstanding_Balance cannot be negative.")
    if payment_status is None:
        payment_status = _payment_status(voucher_total, total_received)

    params = {
        "voucher_number": voucher_number,
        "total_received": total_received,
        "outstanding_balance": outstanding_balance,
    }
    filters = []
    if invoice_date:
        params["invoice_date"] = invoice_date
        filters.append('AND "Date" = %(invoice_date)s')
    if customer:
        params["customer"] = customer
        filters.append('AND COALESCE("Customer", \'\') = %(customer)s')
    if sector == "Farm":
        sql = f'''
            WITH voucher_rows AS (
              SELECT
                id,
                COALESCE("Total_Amount", 0) AS row_total,
                COALESCE(
                  SUM(COALESCE("Total_Amount", 0)) OVER (
                    ORDER BY "Date" NULLS LAST, id
                    ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
                  ),
                  0
                ) AS prior_total,
                ROW_NUMBER() OVER (ORDER BY "Date" DESC NULLS FIRST, id DESC) AS reverse_row_number
              FROM {_farm_transection_table_ref()}
              WHERE COALESCE(__nc_deleted, false) = false
                AND "Invoice_Number"::text = %(voucher_number)s
                {" ".join(filters)}
            ),
            allocated AS (
              SELECT
                id,
                GREATEST(LEAST(%(total_received)s - prior_total, row_total), 0)
                  + CASE
                      WHEN reverse_row_number = 1
                      THEN GREATEST(%(total_received)s - %(voucher_total)s, 0)
                      ELSE 0
                    END AS row_received
              FROM voucher_rows
            )
            UPDATE {_farm_transection_table_ref()} target
            SET
              "Total_Received" = allocated.row_received,
              "Outstanding_Balance" = GREATEST(COALESCE(target."Total_Amount", 0) - allocated.row_received, 0),
              "Payment_Status" = CASE
                WHEN GREATEST(COALESCE(target."Total_Amount", 0) - allocated.row_received, 0) = 0
                     AND allocated.row_received > 0 THEN 'Paid'
                WHEN allocated.row_received > 0 THEN 'Partial'
                ELSE 'Outstanding'
              END
            FROM allocated
            WHERE target.id = allocated.id
            '''
        if connection is None:
            _execute(
                sql,
                {**params, "voucher_total": voucher_total},
            )
        else:
            _execute_in_connection(
                connection,
                sql,
                {**params, "voucher_total": voucher_total},
            )
    elif sector == "Sote Phwar":
        sote_filters = []
        if invoice_date:
            sote_filters.append('AND "Invoice_Date" = %(invoice_date)s')
        if customer:
            sote_filters.append('AND COALESCE("Customer_Name", \'\') = %(customer)s')
        sql = f'''
            WITH voucher_rows AS (
              SELECT
                id,
                COALESCE("Total_Amount", 0) AS row_total,
                COALESCE(
                  SUM(COALESCE("Total_Amount", 0)) OVER (
                    ORDER BY "Invoice_Date" NULLS LAST, id
                    ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
                  ),
                  0
                ) AS prior_total,
                ROW_NUMBER() OVER (ORDER BY "Invoice_Date" DESC NULLS FIRST, id DESC) AS reverse_row_number
              FROM {_sotephwar_transection_table_ref()}
              WHERE COALESCE(__nc_deleted, false) = false
                AND "Invoice_Number"::text = %(voucher_number)s
                {" ".join(sote_filters)}
            ),
            allocated AS (
              SELECT
                id,
                GREATEST(LEAST(%(total_received)s - prior_total, row_total), 0)
                  + CASE
                      WHEN reverse_row_number = 1
                      THEN GREATEST(%(total_received)s - %(voucher_total)s, 0)
                      ELSE 0
                    END AS row_received
              FROM voucher_rows
            )
            UPDATE {_sotephwar_transection_table_ref()} target
            SET
              "Total_Received" = allocated.row_received,
              "Outstanding_Balance" = GREATEST(COALESCE(target."Total_Amount", 0) - allocated.row_received, 0),
              "Payment_Status" = CASE
                WHEN GREATEST(COALESCE(target."Total_Amount", 0) - allocated.row_received, 0) = 0
                     AND allocated.row_received > 0 THEN 'Paid'
                WHEN allocated.row_received > 0 THEN 'Partial'
                ELSE 'Outstanding'
              END
            FROM allocated
            WHERE target.id = allocated.id
            '''
        if connection is None:
            _execute(
                sql,
                {**params, "voucher_total": voucher_total},
            )
        else:
            _execute_in_connection(
                connection,
                sql,
                {**params, "voucher_total": voucher_total},
            )

    return {
        "voucher_total": voucher_total,
        "total_received": total_received,
        "outstanding_balance": outstanding_balance,
        "payment_status": payment_status,
    }


def save_payment_receive(
    sector,
    voucher_number,
    receive_amount,
    payment_method="",
    reference_number="",
    notes="",
    recorded_by="",
    receive_date=None,
    invoice_date=None,
    customer=None,
):
    ensure_payment_receive_table()
    ensure_voucher_summary_fields()
    receive_amount = int(receive_amount or 0)
    if receive_amount <= 0:
        raise ValueError("receive_amount must be greater than zero")

    with _connect() as connection:
        try:
            with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                _lock_payment_voucher(
                    connection,
                    sector,
                    voucher_number,
                    invoice_date=invoice_date,
                    customer=customer,
                )
                voucher = _payment_voucher_lookup(
                    sector,
                    voucher_number,
                    connection=connection,
                    invoice_date=invoice_date,
                    customer=customer,
                )
                if not voucher:
                    raise LookupError("Voucher not found")
                invoice_amount = int(voucher.get("invoice_amount") or 0)
                history_received = _payment_receive_total(
                    sector,
                    voucher_number,
                    connection=connection,
                    invoice_date=invoice_date,
                    customer=customer,
                )
                previous_paid = max(
                    history_received,
                    int(voucher.get("current_received") or 0),
                )
                outstanding_balance = invoice_amount - (previous_paid + receive_amount)
                if outstanding_balance < 0:
                    logger.error(
                        "Rejecting payment save for %s %s: invoice_amount=%s previous_paid=%s receive_amount=%s outstanding_balance=%s",
                        sector,
                        voucher_number,
                        invoice_amount,
                        previous_paid,
                        receive_amount,
                        outstanding_balance,
                    )
                    raise ValueError("Outstanding_Balance cannot be negative.")

                insert_row = _fetch_one_in_connection(
                    connection,
                    f'''
                    INSERT INTO {_payment_receive_table_ref()}
                      ("Receive_Date", "Sector", "Voucher_Number", "Invoice_Date", "Customer", "Invoice_Amount",
                       "Previous_Paid", "Receive_Amount", "Outstanding_Balance", "Payment_Method",
                       "Reference_Number", "Notes", "Recorded_By")
                    VALUES
                      (%(receive_date)s, %(sector)s, %(voucher_number)s, %(invoice_date)s, %(customer)s, %(invoice_amount)s,
                       %(previous_paid)s, %(receive_amount)s, %(outstanding_balance)s, %(payment_method)s,
                       %(reference_number)s, %(notes)s, %(recorded_by)s)
                    RETURNING
                      id,
                      "Receive_Date" AS receive_date,
                      "Sector" AS sector,
                      "Voucher_Number" AS voucher_number,
                      "Invoice_Date" AS invoice_date,
                      "Customer" AS customer,
                      "Invoice_Amount" AS invoice_amount,
                      "Previous_Paid" AS previous_paid,
                      "Receive_Amount" AS receive_amount,
                      "Outstanding_Balance" AS outstanding_balance,
                      "Payment_Method" AS payment_method,
                      "Reference_Number" AS reference_number,
                      "Notes" AS notes,
                      "Recorded_By" AS recorded_by
                    ''',
                    {
                        "receive_date": receive_date or date.today(),
                        "sector": sector,
                        "voucher_number": voucher_number,
                        "invoice_date": invoice_date or voucher.get("invoice_date"),
                        "customer": customer or voucher.get("customer") or "",
                        "invoice_amount": invoice_amount,
                        "previous_paid": previous_paid,
                        "receive_amount": receive_amount,
                        "outstanding_balance": outstanding_balance,
                        "payment_method": payment_method,
                        "reference_number": reference_number,
                        "notes": notes,
                        "recorded_by": recorded_by,
                    },
                )
                summary = _update_voucher_payment_summary(
                    sector,
                    voucher_number,
                    connection=connection,
                    invoice_date=invoice_date,
                    customer=customer,
                    total_received=previous_paid + receive_amount,
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    for field in ("invoice_amount", "previous_paid", "receive_amount", "outstanding_balance"):
        insert_row[field] = int(insert_row.get(field) or 0)
    if insert_row.get("receive_date"):
        insert_row["receive_date"] = insert_row["receive_date"].isoformat()
    if insert_row.get("invoice_date") and hasattr(insert_row["invoice_date"], "isoformat"):
        insert_row["invoice_date"] = insert_row["invoice_date"].isoformat()

    return {"payment": insert_row, "summary": summary}


def sync_voucher_payment_summaries():
    ensure_payment_receive_table()
    ensure_voucher_summary_fields()
    vouchers = []
    farm_rows = _fetch_all(
        f'''
        SELECT DISTINCT
          "Invoice_Number"::text AS voucher_number,
          "Date" AS invoice_date,
          COALESCE("Customer", '') AS customer
        FROM {_farm_transection_table_ref()}
        WHERE COALESCE(__nc_deleted, false) = false
          AND "Invoice_Number" IS NOT NULL
        ORDER BY "Invoice_Number"::text, "Date", COALESCE("Customer", '')
        '''
    )
    vouchers.extend(("Farm", row["voucher_number"], row["invoice_date"], row["customer"]) for row in farm_rows)

    sote_rows = _fetch_all(
        f'''
        SELECT DISTINCT
          "Invoice_Number"::text AS voucher_number,
          "Invoice_Date" AS invoice_date,
          COALESCE("Customer_Name", '') AS customer
        FROM {_sotephwar_transection_table_ref()}
        WHERE COALESCE(__nc_deleted, false) = false
          AND "Invoice_Number" IS NOT NULL
        ORDER BY "Invoice_Number"::text, "Invoice_Date", COALESCE("Customer_Name", '')
        '''
    )
    vouchers.extend(("Sote Phwar", row["voucher_number"], row["invoice_date"], row["customer"]) for row in sote_rows)

    updated = 0
    for sector, voucher_number, invoice_date, customer in vouchers:
        _update_voucher_payment_summary(
            sector,
            voucher_number,
            invoice_date=invoice_date,
            customer=customer,
        )
        updated += 1
    return {"updated": updated}


def payment_receive_insert(question):
    values = _parse_payment_receive(question)
    missing = []
    if not values.get("sector"):
        missing.append("sector Farm or Sote Phwar")
    if not values.get("voucher_number"):
        missing.append("voucher number")
    if not values.get("receive_amount"):
        missing.append("receive amount")
    if missing:
        return {
            "formula": "payment_receive_insert",
            "period": "all_time",
            "inserted": False,
            "missing": missing,
            "values": values,
        }

    try:
        saved = save_payment_receive(
            sector=values["sector"],
            voucher_number=values["voucher_number"],
            receive_amount=values["receive_amount"],
            payment_method=values.get("payment_method") or "",
            reference_number=values.get("reference_number") or "",
            notes=values.get("notes") or "",
            recorded_by=values.get("recorded_by") or "Telegram Finance Bot",
            receive_date=values.get("receive_date"),
        )
        return {
            "formula": "payment_receive_insert",
            "period": "all_time",
            "inserted": True,
            **saved,
        }
    except LookupError:
        return {
            "formula": "payment_receive_insert",
            "period": "all_time",
            "inserted": False,
            "missing": ["matching voucher"],
            "values": values,
        }
    except ValueError as exc:
        return {
            "formula": "payment_receive_insert",
            "period": "all_time",
            "inserted": False,
            "error": str(exc),
            "values": values,
        }


def payment_receive_summary(period="all_time", sector=None, limit=10):
    ensure_payment_receive_table()
    date_sql, params = _date_filter_for_column(period, "invoices.invoice_date")
    sector_sql = ""
    if sector:
        sector_sql = "AND invoices.sector = %(sector)s"
        params["sector"] = sector

    rows = _fetch_all(
        f'''
        WITH invoices AS (
          SELECT
            'Farm' AS sector,
            COALESCE(f."Invoice_Number"::text, '') AS voucher_number,
            MIN(f."Date") AS invoice_date,
            MIN(COALESCE({_linked_farm_customer_expr("f")}, '')) AS customer,
            COALESCE(SUM(f."Total_Amount"), 0) AS invoice_amount,
            COALESCE(SUM(f."Total_Received"), 0) AS received_amount,
            COALESCE(SUM(f."Outstanding_Balance"), 0) AS outstanding_balance
          FROM {_farm_transection_table_ref()} f
          {_farm_customer_link_join("f")}
          WHERE COALESCE(f.__nc_deleted, false) = false
            AND f."Invoice_Number" IS NOT NULL
            AND f."Total_Amount" IS NOT NULL
          GROUP BY f."Invoice_Number"::text
          UNION ALL
          SELECT
            'Sote Phwar' AS sector,
            COALESCE(s."Invoice_Number"::text, '') AS voucher_number,
            MIN(s."Invoice_Date") AS invoice_date,
            MIN(COALESCE({_linked_customer_expr("s")}, '')) AS customer,
            COALESCE(SUM(s."Total_Amount"), 0) AS invoice_amount,
            COALESCE(SUM(s."Total_Received"), 0) AS received_amount,
            COALESCE(SUM(s."Outstanding_Balance"), 0) AS outstanding_balance
          FROM {_sotephwar_transection_table_ref()} s
          {_sotephwar_customer_link_join("s")}
          WHERE COALESCE(s.__nc_deleted, false) = false
            AND s."Invoice_Number" IS NOT NULL
            AND s."Total_Amount" IS NOT NULL
          GROUP BY s."Invoice_Number"::text
        ),
        payments AS (
          SELECT
            "Sector" AS sector,
            "Voucher_Number" AS voucher_number,
            MAX("Receive_Date") AS last_receive_date
          FROM {_payment_receive_table_ref()}
          GROUP BY "Sector", "Voucher_Number"
        )
        SELECT
          invoices.sector,
          invoices.voucher_number,
          invoices.invoice_date,
          invoices.customer,
          COALESCE(invoices.invoice_amount, 0) AS invoice_amount,
          COALESCE(invoices.received_amount, 0) AS received_amount,
          COALESCE(invoices.outstanding_balance, 0) AS outstanding_balance,
          payments.last_receive_date,
          GREATEST(CURRENT_DATE - COALESCE(invoices.invoice_date::date, CURRENT_DATE), 0) AS age_days
        FROM invoices
        LEFT JOIN payments
          ON payments.sector = invoices.sector
         AND payments.voucher_number = invoices.voucher_number
        WHERE COALESCE(invoices.invoice_amount, 0) > 0
          {date_sql}
          {sector_sql}
        ORDER BY outstanding_balance DESC NULLS LAST, invoices.invoice_date NULLS LAST
        ''',
        params,
    )

    total_invoice_amount = 0
    total_received = 0
    outstanding_receivables = 0
    aging = {"0-30": 0, "31-60": 0, "61-90": 0, "90+": 0}
    customer_balances = {}
    sector_totals = {}
    invoices = []
    for row in rows:
        invoice_amount = int(row.get("invoice_amount") or 0)
        received_amount = int(row.get("received_amount") or 0)
        outstanding = int(row.get("outstanding_balance") or 0)
        age_days = int(row.get("age_days") or 0)
        total_invoice_amount += invoice_amount
        total_received += received_amount
        outstanding_receivables += outstanding
        bucket = "0-30" if age_days <= 30 else "31-60" if age_days <= 60 else "61-90" if age_days <= 90 else "90+"
        aging[bucket] += max(outstanding, 0)
        customer = row.get("customer") or "-"
        customer_balances[customer] = customer_balances.get(customer, 0) + outstanding
        sector_name = row.get("sector") or "-"
        sector_row = sector_totals.setdefault(
            sector_name,
            {"sector": sector_name, "invoice_amount": 0, "received_amount": 0, "outstanding_balance": 0},
        )
        sector_row["invoice_amount"] += invoice_amount
        sector_row["received_amount"] += received_amount
        sector_row["outstanding_balance"] += outstanding
        row["invoice_amount"] = invoice_amount
        row["received_amount"] = received_amount
        row["outstanding_balance"] = outstanding
        row["age_days"] = age_days
        row["aging_bucket"] = bucket
        invoices.append(row)

    top_customer_balances = [
        {"customer": customer, "outstanding_balance": balance}
        for customer, balance in sorted(customer_balances.items(), key=lambda item: item[1], reverse=True)
        if balance != 0
    ][:limit]

    return {
        "formula": "payment_receive_summary",
        "period": period,
        "sector": sector,
        "total_invoice_amount": total_invoice_amount,
        "total_received": total_received,
        "outstanding_receivables": outstanding_receivables,
        "collection_rate_percent": round((total_received / total_invoice_amount) * 100, 2) if total_invoice_amount else 0,
        "aging": aging,
        "customer_balances": top_customer_balances,
        "sector_totals": list(sector_totals.values()),
        "invoices": invoices[:limit],
    }


def _master_bucket_sql(granularity, column_name):
    if granularity not in {"day", "week", "month", "year"}:
        granularity = "month"
    return f"TO_CHAR(DATE_TRUNC('{granularity}', {column_name}), " + {
        "day": "'YYYY-MM-DD'",
        "week": "'IYYY-\"W\"IW'",
        "month": "'YYYY-MM'",
        "year": "'YYYY'",
    }[granularity] + ")"


def _master_comparison_ai_comment(rows, categories=None, compare_mode=None):
    if not rows:
        return "No matching master usage found for this enquiry."
    top = max(rows, key=lambda row: int(row.get("amount") or 0))
    category_text = ""
    if categories:
        category_text = f" for {', '.join(categories[:3])}"
        if len(categories) > 3:
            category_text += f" and {len(categories) - 3} more"
    mode_text = "same-category" if compare_mode == "same" else "different-category" if compare_mode == "different" else "master"
    return (
        f"{mode_text.title()} enquiry{category_text}: highest amount is "
        f"{top.get('master_name') or '-'} in {top.get('period_bucket') or '-'}."
    )


def master_name_comparison(period="this_year", scope="both", granularity="month", limit=50, categories=None, compare_mode=None):
    scope = scope if scope in {"category", "customer", "both"} else "both"
    granularity = granularity if granularity in {"day", "week", "month", "year"} else "month"
    limit = max(1, min(int(limit or 50), 200))
    categories = [str(category).strip() for category in (categories or []) if str(category).strip()]
    rows = []

    if scope in {"category", "both"}:
        date_sql, params = _date_filter_for_column(period, 't."Date"')
        category_filter_sql = ""
        if categories:
            category_filter_sql = '''
              AND COALESCE(cm."category_name", NULLIF(TRIM(t."Categorization"), '')) = ANY(%(categories)s)
            '''
            params = {**params, "categories": categories}
        category_rows = _fetch_all(
            f'''
            SELECT
              'category' AS master_type,
              {_master_bucket_sql(granularity, 't."Date"')} AS period_bucket,
              COALESCE(cm."category_name", NULLIF(TRIM(t."Categorization"), ''), '-') AS master_name,
              t."Income_Expense" AS income_expense,
              t."Sector" AS sector,
              COALESCE(SUM(t."Amount"), 0) AS amount,
              COALESCE(SUM(t."Amount"), 0) AS amount_received,
              0 AS outstanding_amount,
              COUNT(*) AS row_count,
              COUNT(cm."category_name") AS linked_count
            FROM {_table_ref()} t
            {_transaction_category_link_join("t")}
            WHERE COALESCE(t.__nc_deleted, false) = false
              {date_sql}
              {category_filter_sql}
            GROUP BY
              DATE_TRUNC('{granularity}', t."Date"),
              COALESCE(cm."category_name", NULLIF(TRIM(t."Categorization"), ''), '-'),
              t."Income_Expense",
              t."Sector"
            ''',
            params,
        )
        rows.extend(category_rows)

    if scope in {"customer", "both"}:
        farm_date_sql, farm_params = _date_filter_for_column(period, 'f."Date"')
        farm_rows = _fetch_all(
            f'''
            SELECT
              'customer' AS master_type,
              {_master_bucket_sql(granularity, 'f."Date"')} AS period_bucket,
              COALESCE(cust."customer_name", NULLIF(TRIM(f."Customer"), ''), '-') AS master_name,
              'Income' AS income_expense,
              'Farm' AS sector,
              COALESCE(SUM(f."Total_Amount"), 0) AS amount,
              COALESCE(SUM(f."Total_Received"), 0) AS amount_received,
              COALESCE(SUM(f."Outstanding_Balance"), 0) AS outstanding_amount,
              COUNT(*) AS row_count,
              COUNT(cust."customer_name") AS linked_count
            FROM {_farm_transection_table_ref()} f
            {_farm_customer_link_join("f")}
            WHERE COALESCE(f.__nc_deleted, false) = false
              {farm_date_sql}
            GROUP BY
              DATE_TRUNC('{granularity}', f."Date"),
              COALESCE(cust."customer_name", NULLIF(TRIM(f."Customer"), ''), '-')
            ''',
            farm_params,
        )
        rows.extend(farm_rows)

        sote_date_sql, sote_params = _date_filter_for_column(period, 's."Invoice_Date"')
        sote_rows = _fetch_all(
            f'''
            SELECT
              'customer' AS master_type,
              {_master_bucket_sql(granularity, 's."Invoice_Date"')} AS period_bucket,
              COALESCE(cust."customer_name", NULLIF(TRIM(s."Customer_Name"), ''), '-') AS master_name,
              'Income' AS income_expense,
              'Sote Phwar' AS sector,
              COALESCE(SUM(s."Total_Amount"), 0) AS amount,
              COALESCE(SUM(s."Total_Received"), 0) AS amount_received,
              COALESCE(SUM(s."Outstanding_Balance"), 0) AS outstanding_amount,
              COUNT(*) AS row_count,
              COUNT(cust."customer_name") AS linked_count
            FROM {_sotephwar_transection_table_ref()} s
            {_sotephwar_customer_link_join("s")}
            WHERE COALESCE(s.__nc_deleted, false) = false
              {sote_date_sql}
            GROUP BY
              DATE_TRUNC('{granularity}', s."Invoice_Date"),
              COALESCE(cust."customer_name", NULLIF(TRIM(s."Customer_Name"), ''), '-')
            ''',
            sote_params,
        )
        rows.extend(sote_rows)

    for row in rows:
        row["amount"] = int(row.get("amount") or 0)
        row["amount_received"] = int(row.get("amount_received") or 0)
        row["outstanding_amount"] = int(row.get("outstanding_amount") or 0)
        row["row_count"] = int(row.get("row_count") or 0)
        row["linked_count"] = int(row.get("linked_count") or 0)
        row["unlinked_count"] = max(0, row["row_count"] - row["linked_count"])

    rows = sorted(
        rows,
        key=lambda row: (str(row.get("period_bucket") or ""), row.get("master_type") or "", -int(row.get("amount") or 0)),
    )
    totals = {}
    for row in rows:
        bucket = row.get("period_bucket") or "-"
        totals.setdefault(bucket, {"period_bucket": bucket, "amount": 0, "amount_received": 0, "outstanding_amount": 0, "row_count": 0, "unlinked_count": 0})
        totals[bucket]["amount"] += row["amount"]
        totals[bucket]["amount_received"] += row["amount_received"]
        totals[bucket]["outstanding_amount"] += row["outstanding_amount"]
        totals[bucket]["row_count"] += row["row_count"]
        totals[bucket]["unlinked_count"] += row["unlinked_count"]
    total_amount = sum(row["amount"] for row in rows)
    amount_received = sum(row["amount_received"] for row in rows)
    outstanding_amount = sum(row["outstanding_amount"] for row in rows)

    return {
        "formula": "master_name_comparison",
        "period": period,
        "scope": scope,
        "granularity": granularity,
        "compare_mode": compare_mode,
        "selected_categories": categories,
        "total_amount": total_amount,
        "amount_received": amount_received,
        "outstanding_amount": outstanding_amount,
        "totals": list(totals.values()),
        "rows": rows[:limit],
        "row_count": len(rows),
        "ai_comment": _master_comparison_ai_comment(rows, categories=categories, compare_mode=compare_mode),
    }


FORMULAS = {
    "sales_total": sales_total,
    "expense_total": expense_total,
    "gross_profit": gross_profit,
    "kpi_overview": kpi_overview,
    "cash_flow": cash_flow,
    "sector_summary": sector_summary,
    "category_summary": category_summary,
    "top_expenses": top_expenses,
    "top_income": top_income,
    "list_transactions": list_transactions,
    "farm_transection_customer": farm_transection_customer,
    "sotephwar_transection_summary": sotephwar_transection_summary,
    "sotephwar_transection_monthly_summary": sotephwar_transection_monthly_summary,
    "sotephwar_transection_top": sotephwar_transection_top,
    "sotephwar_transection_list": sotephwar_transection_list,
    "sotephwar_transection_quantity": sotephwar_transection_quantity,
    "sotephwar_transection_customer": sotephwar_transection_customer,
    "sotephwar_payment_update": sotephwar_payment_update,
    "sotephwar_inventory_stock": sotephwar_inventory_stock,
    "sotephwar_inventory_movement_summary": sotephwar_inventory_movement_summary,
    "sotephwar_inventory_list": sotephwar_inventory_list,
    "financial_obligation_summary": financial_obligation_summary,
    "financial_obligation_due": financial_obligation_due,
    "financial_obligation_list": financial_obligation_list,
    "financial_obligation_insert": financial_obligation_insert,
    "payment_receive_insert": payment_receive_insert,
    "payment_receive_summary": payment_receive_summary,
    "master_name_comparison": master_name_comparison,
}


def choose_formula_by_keywords(question):
    text = question.lower()
    period = normalize_period(question)
    sotephwar_customer = _sotephwar_customer_filter(question)
    farm_customer = _farm_customer_filter(question)

    if is_financial_obligation_question(question):
        normalized = _normalized_text(question)
        if _financial_obligation_insert_requested(question):
            return "financial_obligation_insert"
        if "due" in normalized or "upcoming" in normalized or "overdue" in normalized:
            return "financial_obligation_due"
        if "list" in normalized or "show" in normalized or "detail" in normalized or "creditor" in normalized:
            return "financial_obligation_list"
        return "financial_obligation_summary"

    if is_payment_receive_question(question):
        if _payment_receive_insert_requested(question):
            return "payment_receive_insert"
        return "payment_receive_summary"

    if is_master_comparison_question(question):
        return "master_name_comparison"

    if is_sotephwar_inventory_question(question):
        normalized = _normalized_text(question)
        if (
            "list" in normalized
            or "show" in normalized
            or "movement" in normalized
            or "movements" in normalized
            or period.startswith("date:")
        ):
            return "sotephwar_inventory_list"
        if "summary" in normalized or "production" in normalized or "transfer" in normalized or "sale" in normalized:
            return "sotephwar_inventory_movement_summary"
        return "sotephwar_inventory_stock"

    if _sotephwar_payment_update_requested(question):
        return "sotephwar_payment_update"

    if is_sotephwar_transection_question(question):
        if sotephwar_customer or "customer" in text or "voucher" in text:
            return "sotephwar_transection_customer"
        if _month_by_month_requested(question):
            return "sotephwar_transection_monthly_summary"
        if (
            "quantity" in text
            or "bottle" in text
            or "bottles" in text
            or "sell" in text
            or "sold" in text
            or "sale quantity" in text
            or _sotephwar_item_filter(question)
        ):
            return "sotephwar_transection_quantity"
        if "top" in text or "biggest" in text or "largest" in text or "highest" in text:
            return "sotephwar_transection_top"
        if period.startswith("date:") or "list" in text or "show" in text or "invoice" in text:
            return "sotephwar_transection_list"
        return "sotephwar_transection_summary"

    if _sotephwar_income_summary_question(question):
        if _month_by_month_requested(question):
            return "sotephwar_transection_monthly_summary"
        if "top" not in text and "biggest" not in text and "largest" not in text and "highest" not in text:
            return "sotephwar_transection_summary"

    if _sotephwar_voucher_question(question):
        return "sotephwar_transection_customer"

    if (
        ("voucher" in text or "vouchers" in text or "invoice" in text or "invoices" in text)
        and _sotephwar_customer_search_text(question)
    ):
        return "sotephwar_transection_customer"

    if (
        sotephwar_customer
        and (
            "transaction" in text
            or "transection" in text
            or "voucher" in text
            or "invoice" in text
        )
    ):
        return "sotephwar_transection_customer"

    if (
        ("transaction" in text or "transection" in text)
        and (" of " in f" {text} " or " for " in f" {text} ")
        and not normalize_period(question).startswith("date:")
    ):
        return "sotephwar_transection_customer"

    if farm_customer:
        return "sales_total"

    if "subgroup" in text or "sub group" in text or "transaction group" in text or "transection group" in text:
        return "category_summary"
    if period.startswith("date:") and (
        "transaction" in text
        or "transection" in text
        or "record" in text
        or "list" in text
        or "show" in text
    ):
        return "list_transactions"
    if _detail_requested(question):
        return "list_transactions"
    if "cash" in text or "cash flow" in text:
        return "cash_flow"
    if (
        "top expense" in text
        or "top expenses" in text
        or re.search(r"\btop\s+\d{1,2}\s+expenses?\b", text)
        or re.search(r"\btop\s+\d{1,2}\b.*\b(?:expense|expenses|cost|costs|spend|spending)\b", text)
        or "biggest expense" in text
        or "largest expense" in text
        or "highest expense" in text
    ):
        return "top_expenses"
    if (
        "top income" in text
        or "top incomes" in text
        or "top customer" in text
        or "top customers" in text
        or "top sale" in text
        or "top sales" in text
        or "biggest income" in text
        or "biggest customer" in text
        or "biggest customers" in text
        or "largest income" in text
        or "largest customer" in text
        or "largest customers" in text
        or "highest income" in text
        or "highest customer" in text
        or "highest customers" in text
        or re.search(r"\btop\s+\d{1,2}\s+(?:income|incomes|sales?)\b", text)
        or re.search(r"\btop\s+\d{1,2}\s+customers?\b", text)
        or re.search(r"\btop\s+\d{1,2}\b.*\b(?:income|incomes|sales?|revenue)\b", text)
        or re.search(r"\btop\s+\d{1,2}\b.*\bcustomers?\b", text)
    ):
        return "top_income"
    if (
        ("summary" in text or "summaries" in text or "report" in text)
        and ("income" in text or "sale" in text or "sales" in text or "revenue" in text)
    ):
        return "category_summary"
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
    if formula_name in ("top_expenses", "top_income"):
        return formula(period, filters, limit=extract_top_limit(question))
    if formula_name == "list_transactions":
        text = _normalized_text(question)
        if "income_expense" not in filters:
            if any(_contains_phrase(text, word) for word in ("expense", "cost", "spend", "spending")):
                filters["income_expense"] = "Expense"
            elif any(_contains_phrase(text, word) for word in ("income", "sale", "sales", "revenue")):
                filters["income_expense"] = "Income"
        default_limit = 50 if _detail_requested(question) else 20
        return formula(period, filters, limit=extract_top_limit(question, default=default_limit))
    if formula_name in ("sotephwar_transection_top", "sotephwar_transection_list"):
        if formula_name == "sotephwar_transection_list":
            return formula(
                period,
                limit=extract_top_limit(question, default=20),
                unpaid_only=_sotephwar_unpaid_filter(question),
            )
        return formula(period, limit=extract_top_limit(question))
    if formula_name == "sotephwar_transection_summary":
        return formula(period)
    if formula_name == "sotephwar_transection_monthly_summary":
        text = _normalized_text(question)
        if "to now" in text or "until now" in text or "up to now" in text:
            period = "this_year"
        return formula(period if period != "all_time" else "this_year")
    if formula_name == "sotephwar_transection_quantity":
        return formula(period, item=_sotephwar_item_filter(question))
    if formula_name == "sotephwar_transection_customer":
        customer_match = _sotephwar_customer_match(question)
        voucher_limit = 200 if _pdf_requested(question) else 50
        if customer_match.confidence == "ambiguous":
            return {
                "formula": "sotephwar_transection_customer",
                "period": period,
                "customer": None,
                "unpaid_only": _sotephwar_unpaid_filter(question),
                "invoice_numbers": _sotephwar_invoice_numbers(question),
                "include_note": _sotephwar_note_requested(question),
                "customer_match": {
                    "confidence": customer_match.confidence,
                    "query": customer_match.query,
                    "reason": customer_match.reason,
                    "candidates": list(customer_match.candidates),
                },
                "invoices": [],
            }
        return formula(
            period,
            customer=customer_match.value if customer_match.safe else None,
            limit=extract_top_limit(question, default=voucher_limit, maximum=200),
            unpaid_only=_sotephwar_unpaid_filter(question),
            invoice_numbers=_sotephwar_invoice_numbers(question),
            include_note=_sotephwar_note_requested(question),
        )
    if formula_name == "sotephwar_payment_update":
        return formula(question)
    if formula_name == "sotephwar_inventory_stock":
        return formula(
            product=_sotephwar_item_filter(question),
            store=_sotephwar_inventory_store_filter(question),
        )
    if formula_name == "sotephwar_inventory_movement_summary":
        return formula(
            period,
            product=_sotephwar_item_filter(question),
            store=_sotephwar_inventory_store_filter(question),
            movement_type=_sotephwar_inventory_type_filter(question),
        )
    if formula_name == "sotephwar_inventory_list":
        return formula(
            period,
            product=_sotephwar_item_filter(question),
            store=_sotephwar_inventory_store_filter(question),
            movement_type=_sotephwar_inventory_type_filter(question),
            limit=extract_top_limit(question, default=20),
        )
    if formula_name == "financial_obligation_insert":
        return formula(question)
    if formula_name == "financial_obligation_summary":
        return formula(
            status=_financial_obligation_status_filter(question),
            category=_financial_obligation_category_filter(question),
        )
    if formula_name == "financial_obligation_due":
        status = _financial_obligation_status_filter(question)
        return formula(
            days=_financial_obligation_due_days(question),
            status=status or "Active",
            category=_financial_obligation_category_filter(question),
            limit=extract_top_limit(question, default=20),
        )
    if formula_name == "financial_obligation_list":
        return formula(
            status=_financial_obligation_status_filter(question),
            category=_financial_obligation_category_filter(question),
            creditor=_financial_obligation_creditor_filter(question),
            limit=extract_top_limit(question, default=20),
        )
    if formula_name == "payment_receive_insert":
        return formula(question)
    if formula_name == "payment_receive_summary":
        return formula(
            period,
            sector=_normalize_payment_sector(question),
            limit=extract_top_limit(question, default=10),
        )
    if formula_name == "master_name_comparison":
        period = _master_compare_period(question)
        if period == "all_time":
            period = "this_year"
        return formula(
            period,
            scope=_master_compare_scope(question),
            granularity=_master_compare_granularity(question),
            limit=extract_top_limit(question, default=80, maximum=200),
        )
    return formula(period, filters)
