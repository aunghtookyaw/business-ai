from datetime import date, datetime
from decimal import Decimal

import psycopg2
import psycopg2.extras

import config
from tools.formula_engine import (
    _connect,
    _farm_transection_table_ref,
    _financial_obligations_table_ref,
    _sotephwar_inventory_table_ref,
    _sotephwar_transection_table_ref,
    _table_ref,
)
from tools.master_relink_db import relink_inserted_rows


TABLES = {
    "transection": {
        "label": "Transection",
        "table_ref": _table_ref,
        "columns": [
            "Date",
            "Income_Expense",
            "Categorization",
            "Sector",
            "Item_Description",
            "Amount",
            "Payment_Method",
            "Attachement",
            "AI_Comment",
        ],
        "required": ["Date", "Income_Expense", "Amount"],
        "numeric": ["Amount"],
        "date": ["Date"],
    },
    "farm_transection": {
        "label": "Farm_Transection",
        "table_ref": _farm_transection_table_ref,
        "columns": [
            "Date",
            "Customer",
            "Invoice_Number",
            "Total_Amount",
            "Total_Received",
            "Outstanding_Balance",
            "Note",
            "AI_Analysis",
        ],
        "required": ["Date", "Customer", "Total_Amount"],
        "numeric": ["Invoice_Number", "Total_Amount", "Total_Received", "Outstanding_Balance"],
        "date": ["Date"],
    },
    "sotephwar_transection": {
        "label": "Sotephwar_Transection",
        "table_ref": _sotephwar_transection_table_ref,
        "columns": [
            "Invoice_Number",
            "Item",
            "Quantity",
            "Total_Amount",
            "Total_Received",
            "Outstanding_Balance",
            "Note",
            "AI_comment",
            "Invoice_Date",
            "Customer_Name",
            "Attachment",
        ],
        "required": ["Invoice_Date", "Item", "Quantity"],
        "numeric": ["Quantity", "Total_Amount", "Total_Received", "Outstanding_Balance"],
        "date": ["Invoice_Date"],
    },
    "financial_obligations": {
        "label": "Financial_Obligations",
        "table_ref": _financial_obligations_table_ref,
        "columns": [
            "Date",
            "Category",
            "Subcategory",
            "Creditor",
            "Amount",
            "Frequency",
            "Start_Date",
            "Next_Due_Date",
            "Status",
            "Notes",
            "AI_comment",
        ],
        "required": ["Creditor", "Amount", "Next_Due_Date"],
        "numeric": ["Amount"],
        "date": ["Date", "Start_Date", "Next_Due_Date"],
    },
    "sotephwar_inventory": {
        "label": "Sotephwar_Inventory",
        "table_ref": _sotephwar_inventory_table_ref,
        "columns": [
            "Date",
            "Type",
            "From_Store",
            "To_Store",
            "Product",
            "Qty",
            "AI_comment",
            "Note",
            "Attachment",
        ],
        "required": ["Date", "Type", "Product", "Qty"],
        "numeric": ["Qty"],
        "date": ["Date"],
    },
}


def _clean_text(value):
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _clean_number(value, field):
    value = _clean_text(value)
    if value is None:
        return None
    try:
        return int(Decimal(value.replace(",", "")))
    except Exception as exc:
        raise ValueError(f"{field} must be a number") from exc


def _clean_date(value, field):
    if value is None:
        return None
    if isinstance(value, date):
        return value.date() if isinstance(value, datetime) else value
    value = _clean_text(value)
    if value is None:
        return None
    for fmt in (
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y/%d/%m",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%m/%d/%Y",
    ):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"{field} must be a date like YYYY-MM-DD")


def _normalise_row(table_config, row):
    cleaned = {}
    numeric = set(table_config["numeric"])
    date_fields = set(table_config["date"])

    for column in table_config["columns"]:
        value = row.get(column)
        if column in numeric:
            cleaned[column] = _clean_number(value, column)
        elif column in date_fields:
            cleaned[column] = _clean_date(value, column)
        else:
            cleaned[column] = _clean_text(value)

    missing = [
        column
        for column in table_config["required"]
        if cleaned.get(column) in (None, "")
    ]
    if missing:
        raise ValueError("Missing required field(s): " + ", ".join(missing))

    if {"Total_Amount", "Total_Received", "Outstanding_Balance"}.issubset(table_config["columns"]):
        total_amount = cleaned.get("Total_Amount") or 0
        total_received = cleaned.get("Total_Received") or 0
        expected_balance = total_amount - total_received
        if expected_balance < 0:
            raise ValueError("Total_Received cannot be greater than Total_Amount")
        cleaned["Outstanding_Balance"] = expected_balance

    return cleaned


def clean_value_for_column(table_key, column, value):
    """Reuse importer coercion rules for one audited update value."""
    table_config = TABLES[table_key]
    if column not in table_config["columns"]:
        raise ValueError(f"{column} is not an importable {table_config['label']} field")
    if column in table_config["numeric"]:
        return _clean_number(value, column)
    if column in table_config["date"]:
        return _clean_date(value, column)
    return _clean_text(value)


def insert_rows_transactional(connection, table_key, rows, commit=False):
    """Insert validated import rows using one caller-owned transaction."""
    if table_key not in TABLES:
        raise ValueError("Unsupported import table")
    table_config = TABLES[table_key]
    table_ref = table_config["table_ref"]()
    columns = table_config["columns"]
    quoted_columns = ", ".join(f'"{column}"' for column in columns)
    placeholders = ", ".join(f"%({column})s" for column in columns)
    statement = f"""
        INSERT INTO {table_ref}
          ({quoted_columns})
        VALUES
          ({placeholders})
        RETURNING id
    """
    inserted = []
    try:
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            for row in rows:
                cleaned = _normalise_row(table_config, row)
                cursor.execute(statement, cleaned)
                inserted.append({"row_number": row.get("__row_number"), "id": cursor.fetchone()["id"]})
        if commit:
            connection.commit()
        return {"table": table_config["label"], "inserted": inserted, "errors": []}
    except Exception:
        if commit:
            connection.rollback()
        raise


def _insert_rows(connection, table_key, rows):
    table_config = TABLES[table_key]
    table_ref = table_config["table_ref"]()
    columns = table_config["columns"]
    quoted_columns = ", ".join(f'"{column}"' for column in columns)
    placeholders = ", ".join(f"%({column})s" for column in columns)
    sql = f"""
        INSERT INTO {table_ref}
          ({quoted_columns})
        VALUES
          ({placeholders})
        RETURNING id
    """

    inserted = []
    errors = []
    with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        for row in rows:
            row_number = row.get("__row_number")
            try:
                cleaned = _normalise_row(table_config, row)
                cursor.execute(sql, cleaned)
                inserted.append({
                    "row_number": row_number,
                    "id": cursor.fetchone()["id"],
                })
            except Exception as exc:
                connection.rollback()
                errors.append({
                    "row_number": row_number,
                    "error": str(exc),
                })
            else:
                connection.commit()

    return {
        "table": table_config["label"],
        "inserted": inserted,
        "errors": errors,
    }


def import_excel_payload(payload):
    results = {}
    with _connect() as connection:
        for table_key in TABLES:
            rows = payload.get(table_key, [])
            if not rows:
                results[table_key] = {
                    "table": TABLES[table_key]["label"],
                    "inserted": [],
                    "errors": [],
                }
                continue
            results[table_key] = _insert_rows(connection, table_key, rows)
    inserted_ids_by_table = {
        table_key: [
            row["id"]
            for row in result.get("inserted", [])
            if row.get("id") is not None
        ]
        for table_key, result in results.items()
    }
    try:
        results["_master_relink"] = relink_inserted_rows(inserted_ids_by_table)
    except Exception as exc:
        results["_master_relink"] = {}
        results["_master_relink_error"] = str(exc)
    return results
