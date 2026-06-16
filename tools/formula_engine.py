from datetime import date, datetime, time, timedelta
import re
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


def _farm_customer_filter(question):
    text = _normalized_text(question)
    if any(_contains_phrase(text, word) for word in ("expense", "cost", "spend", "spending")):
        return None

    has_income_word = any(_contains_phrase(text, word) for word in ("sale", "sales", "income", "revenue"))
    if has_income_word:
        cleaned = re.sub(r"\b(?:from|by|for|customer|farm|sale|sales|income|revenue|total|summary|summaries|report|reports|show|find|top|biggest|largest|highest|this|last|year|month|week|today|yesterday)\b", " ", text)
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
    query = re.sub(r"\b(?:show|find|tell|me|please|customer|from|for|by|farm|sale|sales|income|revenue|total|summary|summaries|report|reports|top|biggest|largest|highest|this|last|year|month|week|today|yesterday)\b", " ", query)
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
          COALESCE(SUM(f."Total_Due"), 0) AS total_amount,
          COALESCE(SUM(f."Paid"), 0) AS amount_received,
          COALESCE(SUM(COALESCE(f."Total_Due", 0) - COALESCE(f."Paid", 0)), 0) AS outstanding_amount
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
    }
    if not _include_sotephwar_income(filters):
        return empty
    result = sotephwar_transection_summary(period)
    return {
        "invoice_count": int(result.get("invoice_count") or 0),
        "total_amount": int(result.get("total_amount") or 0),
        "amount_received": int(result.get("amount_received") or 0),
        "outstanding_amount": int(result.get("outstanding_amount") or 0),
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
          COALESCE(SUM(f."Total_Due"), 0) AS amount,
          COALESCE(SUM(f."Total_Due"), 0) AS total_amount,
          COALESCE(SUM(f."Paid"), 0) AS amount_received,
          COALESCE(SUM(COALESCE(f."Total_Due", 0) - COALESCE(f."Paid", 0)), 0) AS outstanding_amount,
          COUNT(*) AS invoice_count,
          'Farm_Transection' AS payment_method
        FROM {_farm_transection_table_ref()} f
        {_farm_customer_link_join("f")}
        WHERE COALESCE(f.__nc_deleted, false) = false
          AND f."Total_Due" IS NOT NULL
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
          COALESCE(f."Total_Due", 0) AS total_amount,
          COALESCE(f."Paid", 0) AS amount_received,
          COALESCE(f."Total_Due", 0) - COALESCE(f."Paid", 0) AS outstanding_amount
        FROM {_farm_transection_table_ref()} f
        {_farm_customer_link_join("f")}
        WHERE COALESCE(f.__nc_deleted, false) = false
          AND f."Total_Due" IS NOT NULL
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
    params["limit"] = limit
    rows = _fetch_all(
        f'''
        SELECT
          'Sote Phwar' AS sector,
          'Sote Phwar Sales' AS category,
          COALESCE({_linked_customer_expr("s")}, '') AS item,
          COALESCE({_linked_customer_expr("s")}, '') AS customer_name,
          COALESCE(SUM(s."Total_Amount"), 0) AS amount,
          COALESCE(SUM(s."Total_Amount"), 0) AS total_amount,
          COALESCE(SUM(s."Amount_Received"), 0) AS amount_received,
          COALESCE(SUM(COALESCE(s."Total_Amount", 0) - COALESCE(s."Amount_Received", 0)), 0) AS outstanding_amount,
          COUNT(*) AS invoice_count,
          'Sotephwar_Transection' AS payment_method
        FROM {_sotephwar_transection_table_ref()} s
        {_sotephwar_customer_link_join("s")}
        WHERE COALESCE(s.__nc_deleted, false) = false
          AND s."Total_Amount" IS NOT NULL
          {date_sql}
        GROUP BY COALESCE({_linked_customer_expr("s")}, '')
        ORDER BY amount DESC NULLS LAST
        LIMIT %(limit)s
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
        SELECT COALESCE(SUM(f."Paid"), 0) AS paid
        FROM {_farm_transection_table_ref()} f
        {_farm_customer_link_join("f")}
        WHERE COALESCE(f.__nc_deleted, false) = false
          {farm_filter_sql}
          {date_sql}
        ''',
        params,
    )
    return int(row.get("paid") or 0)


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
              {filter_sql}
              {date_sql}
            ''',
            params,
        )
        transection_total = int(row["total_sales"] or 0)
    farm_summary = _farm_sales_summary(period, filters)
    sotephwar_summary = _sotephwar_income_summary(period, filters)
    farm_total = farm_summary["total_amount"]
    sotephwar_total = sotephwar_summary["total_amount"]
    total_sales = transection_total + farm_total + sotephwar_total
    amount_received = farm_summary["amount_received"] + sotephwar_summary["amount_received"]
    outstanding_amount = farm_summary["outstanding_amount"] + sotephwar_summary["outstanding_amount"]
    return _with_filters({
        "formula": "sales_total",
        "period": period,
        "total_sales": total_sales,
        "amount_received": amount_received,
        "outstanding_amount": outstanding_amount,
        "sources": {
            "transection_income": transection_total,
            "sotephwar_transection_total_amount": sotephwar_total,
            "sotephwar_transection_amount_received": sotephwar_summary["amount_received"],
            "sotephwar_transection_outstanding": sotephwar_summary["outstanding_amount"],
            "farm_transection_total_due": farm_total,
            "farm_transection_paid": farm_summary["amount_received"],
            "farm_transection_remained": farm_summary["outstanding_amount"],
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
              COALESCE(SUM(CASE WHEN t."Income_Expense" = 'Income' THEN t."Amount" ELSE 0 END), 0) AS income,
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
            "farm_transection_total_due": farm_income,
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
              COALESCE(SUM(CASE WHEN t."Income_Expense" = 'Income' THEN t."Amount" ELSE 0 END), 0) AS inflow,
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

    farm_paid = _farm_cash_flow(period, filters)
    if farm_paid:
        total_inflow += farm_paid
        methods.append({
            "payment_method": "Farm_Transection paid",
            "inflow": farm_paid,
            "outflow": 0,
            "net_cash_flow": farm_paid,
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
              COALESCE(SUM(CASE WHEN t."Income_Expense" = 'Income' THEN t."Amount" ELSE 0 END), 0) AS income,
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
              COALESCE(SUM(CASE WHEN t."Income_Expense" = 'Income' THEN t."Amount" ELSE 0 END), 0) AS income,
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

    sotephwar_income = _sotephwar_income_summary(period, filters)["total_amount"]
    if sotephwar_income:
        total_income += sotephwar_income
        total_transactions += 1
        for row in categories:
            if row["sector"] == "Sote Phwar" and row["category"] == "Sote Phwar Sales":
                row["income"] += sotephwar_income
                row["net"] += sotephwar_income
                row["transaction_count"] += 1
                break
        else:
            categories.append({
                "sector": "Sote Phwar",
                "category": "Sote Phwar Sales",
                "income": sotephwar_income,
                "expense": 0,
                "net": sotephwar_income,
                "transaction_count": 1,
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
                    break
            else:
                categories.append({
                    "sector": "Farm",
                    "category": "Farm Sales",
                    "income": farm_income,
                    "expense": 0,
                    "net": farm_income,
                    "transaction_count": farm_count,
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


def sotephwar_transection_summary(period="all_time"):
    date_sql, params = _date_filter_for_column(period, '"Invoice_Date"')
    row = _fetch_one(
        f'''
        SELECT
          COUNT(*) AS invoice_count,
          COALESCE(SUM("Total_Amount"), 0) AS total_amount,
          COALESCE(SUM("Amount_Received"), 0) AS amount_received,
          COALESCE(SUM(COALESCE("Total_Amount", 0) - COALESCE("Amount_Received", 0)), 0) AS outstanding_amount
        FROM {_sotephwar_transection_table_ref()}
        WHERE COALESCE(__nc_deleted, false) = false
          {date_sql}
        ''',
        params,
    )

    return {
        "formula": "sotephwar_transection_summary",
        "period": period,
        "invoice_count": int(row["invoice_count"] or 0),
        "total_amount": int(row["total_amount"] or 0),
        "amount_received": int(row["amount_received"] or 0),
        "outstanding_amount": int(row["outstanding_amount"] or 0),
    }


def sotephwar_transection_monthly_summary(period="this_year"):
    date_sql, params = _date_filter_for_column(period, '"Invoice_Date"')
    rows = _fetch_all(
        f'''
        SELECT
          TO_CHAR(DATE_TRUNC('month', "Invoice_Date"), 'YYYY-MM') AS month,
          COUNT(*) AS invoice_count,
          COALESCE(SUM("Total_Amount"), 0) AS total_amount,
          COALESCE(SUM("Amount_Received"), 0) AS amount_received,
          COALESCE(SUM(COALESCE("Total_Amount", 0) - COALESCE("Amount_Received", 0)), 0) AS outstanding_amount
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
          s."Amount_Received" AS amount_received,
          COALESCE(s."Total_Amount", 0) - COALESCE(s."Amount_Received", 0) AS outstanding_amount
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
        unpaid_sql = 'AND COALESCE("Total_Amount", 0) - COALESCE("Amount_Received", 0) > 0'

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
          s."Amount_Received" AS amount_received,
          COALESCE(s."Total_Amount", 0) - COALESCE(s."Amount_Received", 0) AS outstanding_amount
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
          COALESCE(SUM("Amount_Received"), 0) AS amount_received,
          COALESCE(SUM(COALESCE("Total_Amount", 0) - COALESCE("Amount_Received", 0)), 0) AS outstanding_amount
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
        unpaid_sql = 'AND COALESCE("Total_Amount", 0) - COALESCE("Amount_Received", 0) > 0'
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
          s."Amount_Received" AS amount_received,
          COALESCE(s."Total_Amount", 0) - COALESCE(s."Amount_Received", 0) AS outstanding_amount
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
    rows = _fetch_all(
        f'''
        WITH matched AS (
          SELECT
            id,
            COALESCE("Amount_Received", 0) AS previous_amount_received
          FROM {_sotephwar_transection_table_ref()}
          WHERE COALESCE("__nc_deleted", false) = false
            AND "Invoice_Number"::text = %(invoice_number)s
        ),
        updated AS (
          UPDATE {_sotephwar_transection_table_ref()} target
          SET
            "Amount_Received" = matched.previous_amount_received + %(amount)s,
            "Note" = TRIM(CONCAT_WS(E'\n', NULLIF(target."Note", ''), %(note)s))
          FROM matched
          WHERE target.id = matched.id
          RETURNING
            target.id,
            target."Invoice_Date" AS invoice_date,
            COALESCE(target."Invoice_Number", '') AS invoice_number,
            COALESCE(target."Customer_Name", '') AS customer_name,
            COALESCE(target."Item", '') AS item,
            COALESCE(target."Note", '') AS note,
            COALESCE(target."Quantity", 0) AS quantity,
            COALESCE(target."Total_Amount", 0) AS total_amount,
            target."Amount_Received" AS amount_received,
            matched.previous_amount_received AS previous_amount_received,
            COALESCE(target."Total_Amount", 0) - COALESCE(target."Amount_Received", 0) AS outstanding_amount
        )
        SELECT *
        FROM updated
        ORDER BY invoice_date NULLS LAST, id
        ''',
        {
            "invoice_number": values["invoice_number"],
            "amount": values["amount"],
            "note": note,
        },
    )

    for row in rows:
        row["quantity"] = int(row["quantity"] or 0)
        row["total_amount"] = int(row["total_amount"] or 0)
        row["previous_amount_received"] = int(row["previous_amount_received"] or 0)
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
    return formula(period, filters)
