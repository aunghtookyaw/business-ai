from difflib import SequenceMatcher

from tools import search_intelligence
from tools.formula_engine import (
    _fetch_all,
    _sotephwar_transection_table_ref,
    _dimension_values,
    _table_ref,
)


def _rank_matches(query, values, limit=8):
    normalized_query = search_intelligence.normalize_text(query)
    if len(normalized_query) < 2:
        return []

    rows = []
    for value in values:
        normalized = search_intelligence.normalize_text(value)
        if not normalized:
            continue
        if normalized_query == normalized:
            score = 1.0
        elif search_intelligence.contains_phrase(normalized, normalized_query):
            score = 0.95
        elif all(token in normalized.split() for token in normalized_query.split()):
            score = 0.9
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
    rows = _fetch_all(
        f'''
        SELECT DISTINCT "Customer_Name" AS value
        FROM {_sotephwar_transection_table_ref()}
        WHERE COALESCE(__nc_deleted, false) = false
          AND NULLIF(TRIM("Customer_Name"), '') IS NOT NULL
        ORDER BY "Customer_Name"
        '''
    )
    return [row["value"] for row in rows if row.get("value")]


def category_values(sector=None, income_expense=None):
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
        return [row["value"] for row in rows if row.get("value")]

    values = _dimension_values()
    return values.get("categories") or []


def search_customers(query, limit=8):
    return _rank_matches(query, customer_values(), limit=limit)


def search_categories(query, limit=8, sector=None, income_expense=None):
    return _rank_matches(query, category_values(sector=sector, income_expense=income_expense), limit=limit)
