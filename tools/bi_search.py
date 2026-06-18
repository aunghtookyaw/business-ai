from difflib import SequenceMatcher

from tools import search_intelligence
from tools import master_data
from tools.formula_engine import (
    _fetch_all,
    _farm_transection_table_ref,
    _sotephwar_transection_table_ref,
    _dimension_values,
    _table_ref,
)
import config


QUERY_ALIASES = {
    "pak": "pwint aung kyaw",
    "pwint aung kyaw": "pwint aung kyaw",
}


def _unique_values(values):
    seen = set()
    unique = []
    for value in values:
        value = str(value or "").strip()
        normalized = master_data.normalize_name(value)
        if not value or normalized in seen:
            continue
        seen.add(normalized)
        unique.append(value)
    return unique


def _master_table_ref(table_name):
    return f'"{config.TRANSACTION_SCHEMA}"."{table_name}"'


def _rank_matches(query, values, limit=8):
    normalized_query = search_intelligence.normalize_text(query)
    normalized_query = QUERY_ALIASES.get(normalized_query, normalized_query)
    if len(normalized_query) < 2:
        return []

    rows = []
    for value in values:
        normalized = master_data.normalize_name(value)
        if not normalized:
            continue
        if normalized_query == normalized:
            score = 1.0
        elif search_intelligence.contains_phrase(normalized, normalized_query):
            score = 0.95
        elif all(token in normalized.split() for token in normalized_query.split()):
            score = 0.9
        elif all(
            any(candidate.startswith(token) for candidate in normalized.split())
            for token in normalized_query.split()
        ):
            score = 0.85
        else:
            score = SequenceMatcher(None, normalized_query, normalized).ratio()
        if score >= 0.58:
            rows.append((score, value))

    rows.sort(key=lambda item: (-item[0], item[1]))
    seen = set()
    matches = []
    for score, value in rows:
        if value in seen:
            continue
        seen.add(value)
        matches.append({"value": value, "score": round(score, 3)})
        if len(matches) >= limit:
            break
    return matches


def customer_values():
    master_rows = _fetch_all(
        f'''
        SELECT "customer_name" AS value
        FROM {_master_table_ref("customer_master")}
        WHERE COALESCE(__nc_deleted, false) = false
          AND NULLIF(TRIM("customer_name"), '') IS NOT NULL
        ORDER BY "customer_name"
        '''
    )
    transaction_rows = _fetch_all(
        f'''
        SELECT DISTINCT "Customer_Name" AS value
        FROM {_sotephwar_transection_table_ref()}
        WHERE COALESCE(__nc_deleted, false) = false
          AND NULLIF(TRIM("Customer_Name"), '') IS NOT NULL
        ORDER BY "Customer_Name"
        '''
    )
    farm_rows = _fetch_all(
        f'''
        SELECT DISTINCT "Customer" AS value
        FROM {_farm_transection_table_ref()}
        WHERE COALESCE(__nc_deleted, false) = false
          AND NULLIF(TRIM("Customer"), '') IS NOT NULL
        ORDER BY "Customer"
        '''
    )
    return _unique_values([
        row["value"]
        for row in master_rows + transaction_rows + farm_rows
        if row.get("value")
    ])


def category_values(sector=None, income_expense=None):
    master_rows = _fetch_all(
        f'''
        SELECT "category_name" AS value
        FROM {_master_table_ref("category_master")}
        WHERE COALESCE(__nc_deleted, false) = false
          AND NULLIF(TRIM("category_name"), '') IS NOT NULL
        ORDER BY "category_name"
        '''
    )
    master_values = [row["value"] for row in master_rows if row.get("value")]

    if sector or income_expense:
        clauses = []
        params = {}
        if sector:
            clauses.append('AND "Sector" = %(sector)s')
            params["sector"] = sector
        if income_expense:
            clauses.append('AND "Income_Expense" = %(income_expense)s')
            params["income_expense"] = income_expense
        rows = _fetch_all(
            f'''
            SELECT DISTINCT "Categorization" AS value
            FROM {_table_ref()}
            WHERE COALESCE(__nc_deleted, false) = false
              AND NULLIF(TRIM("Categorization"), '') IS NOT NULL
              {' '.join(clauses)}
            ORDER BY "Categorization"
            ''',
            params,
        )
        transaction_values = [row["value"] for row in rows if row.get("value")]
        return _unique_values(master_values + transaction_values)

    values = _dimension_values()
    return _unique_values(master_values + (values.get("categories") or []))


def search_customers(query, limit=8):
    return _rank_matches(query, customer_values(), limit=limit)


def search_categories(query, limit=8, sector=None, income_expense=None):
    return _rank_matches(query, category_values(sector=sector, income_expense=income_expense), limit=limit)
