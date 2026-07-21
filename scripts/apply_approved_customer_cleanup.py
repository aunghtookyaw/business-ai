"""Apply the business-owner-approved 2026-07-16 Customer Master cleanup.

This is intentionally single-purpose. It aborts on any precondition drift and
prints a JSON audit record only after the transaction commits successfully.
"""
import json
from pathlib import Path
import sys

import psycopg2.extras
from psycopg2 import sql

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
from tools.formula_engine import _connect


DELETE_IDS = (256, 276)
RETAIN_IDS = (90, 248)
CONFLICT_TRANSACTION_ID = 728
OLD_CUSTOMER_ID = 142
NEW_CUSTOMER_ID = 143


def _rows(cursor, statement, params=None):
    cursor.execute(statement, params or ())
    return [dict(row) for row in cursor.fetchall()]


def _link_counts(cursor, schema, customer_ids):
    cursor.execute(
        """
        SELECT table_name
        FROM information_schema.columns
        WHERE table_schema = %s AND column_name = 'customer_master_id'
        ORDER BY table_name
        """,
        (schema,),
    )
    tables = [row["table_name"] for row in cursor.fetchall()]
    result = {}
    for table in tables:
        statement = sql.SQL(
            "SELECT customer_master_id, COUNT(*) AS link_count FROM {}.{} "
            "WHERE customer_master_id = ANY(%s) GROUP BY customer_master_id ORDER BY customer_master_id"
        ).format(sql.Identifier(schema), sql.Identifier(table))
        result[table] = _rows(cursor, statement, (list(customer_ids),))
    return result


def _protected_evidence(cursor, schema):
    transaction = _rows(
        cursor,
        sql.SQL(
            'SELECT id, "Invoice_Number", "Invoice_Date", "Customer_Name", "Item", "Quantity", '
            '"Total_Amount", "Total_Received", "Outstanding_Balance", "Payment_Status", "Note" '
            'FROM {}."Sotephwar_Transection" WHERE id = %s'
        ).format(sql.Identifier(schema)),
        (CONFLICT_TRANSACTION_ID,),
    )
    discrepancy = _rows(
        cursor,
        sql.SQL(
            'SELECT COUNT(*) AS record_count, COALESCE(SUM("Receive_Amount"), 0) AS receive_amount '
            'FROM {}."Payment_Receive" WHERE "Customer" = %s'
        ).format(sql.Identifier(schema)),
        ("Zun Ei Khaing",),
    )
    return {"transaction_728": transaction, "zun_payment_evidence": discrepancy}


def apply_cleanup():
    schema = config.TRANSACTION_SCHEMA
    connection = _connect()
    connection.set_session(isolation_level="SERIALIZABLE", autocommit=False)
    try:
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            masters_before = _rows(
                cursor,
                sql.SQL(
                    'SELECT id, customer_name, "Customer_Code", "Region", created_at, updated_at '
                    'FROM {}.customer_master WHERE id = ANY(%s) ORDER BY id FOR UPDATE'
                ).format(sql.Identifier(schema)),
                (list(RETAIN_IDS + DELETE_IDS + (OLD_CUSTOMER_ID, NEW_CUSTOMER_ID)),),
            )
            found = {row["id"]: row["customer_name"] for row in masters_before}
            expected = {
                90: "Ma Nge", 256: "Ma Nge", 248: "Zun Ei Khaing", 276: "Zun Ei Khaing",
                142: "Pwint Aung Kyaw MDY", 143: "Pwint Aung Kyaw POL",
            }
            if found != expected:
                raise RuntimeError(f"Customer Master precondition changed: {found}")

            links_before = _link_counts(cursor, schema, DELETE_IDS)
            linked = {table: rows for table, rows in links_before.items() if rows}
            if linked:
                raise RuntimeError(f"Duplicate IDs are no longer unlinked: {linked}")

            junction = sql.Identifier("_nc_m2m_Sotephwar_Trans_customer_master")
            conflict_before = _rows(
                cursor,
                sql.SQL(
                    'SELECT customer_master_id, "Sotephwar_Transection_id" FROM {}.{} '
                    'WHERE "Sotephwar_Transection_id" = %s FOR UPDATE'
                ).format(sql.Identifier(schema), junction),
                (CONFLICT_TRANSACTION_ID,),
            )
            if conflict_before != [{
                "customer_master_id": OLD_CUSTOMER_ID,
                "Sotephwar_Transection_id": CONFLICT_TRANSACTION_ID,
            }]:
                raise RuntimeError(f"Conflict link precondition changed: {conflict_before}")

            evidence_before = _protected_evidence(cursor, schema)
            if len(evidence_before["transaction_728"]) != 1:
                raise RuntimeError("SotePhwar transaction 728 is missing or duplicated")

            cursor.execute(
                sql.SQL(
                    'DELETE FROM {}.{} WHERE customer_master_id = %s AND "Sotephwar_Transection_id" = %s'
                ).format(sql.Identifier(schema), junction),
                (OLD_CUSTOMER_ID, CONFLICT_TRANSACTION_ID),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("Expected exactly one conflicting junction deletion")
            cursor.execute(
                sql.SQL(
                    'INSERT INTO {}.{} (customer_master_id, "Sotephwar_Transection_id") VALUES (%s, %s)'
                ).format(sql.Identifier(schema), junction),
                (NEW_CUSTOMER_ID, CONFLICT_TRANSACTION_ID),
            )
            cursor.execute(
                sql.SQL('DELETE FROM {}.customer_master WHERE id = ANY(%s)').format(sql.Identifier(schema)),
                (list(DELETE_IDS),),
            )
            if cursor.rowcount != 2:
                raise RuntimeError("Expected exactly two unlinked duplicate master deletions")

            links_after = _link_counts(cursor, schema, DELETE_IDS)
            conflict_after = _rows(
                cursor,
                sql.SQL(
                    'SELECT customer_master_id, "Sotephwar_Transection_id" FROM {}.{} '
                    'WHERE "Sotephwar_Transection_id" = %s'
                ).format(sql.Identifier(schema), junction),
                (CONFLICT_TRANSACTION_ID,),
            )
            evidence_after = _protected_evidence(cursor, schema)
            retained_after = _rows(
                cursor,
                sql.SQL('SELECT id, customer_name, "Customer_Code" FROM {}.customer_master WHERE id = ANY(%s) ORDER BY id').format(sql.Identifier(schema)),
                (list(RETAIN_IDS),),
            )
            deleted_after = _rows(
                cursor,
                sql.SQL('SELECT id FROM {}.customer_master WHERE id = ANY(%s)').format(sql.Identifier(schema)),
                (list(DELETE_IDS),),
            )
            if any(links_after.values()) or deleted_after:
                raise RuntimeError("Post-change duplicate verification failed")
            if conflict_after != [{
                "customer_master_id": NEW_CUSTOMER_ID,
                "Sotephwar_Transection_id": CONFLICT_TRANSACTION_ID,
            }]:
                raise RuntimeError(f"Post-change conflict link verification failed: {conflict_after}")
            if evidence_before != evidence_after:
                raise RuntimeError("Protected transaction or payment evidence changed")

            audit = {
                "operation": "approved_customer_master_cleanup_20260716",
                "transactional": True,
                "retained_ids": list(RETAIN_IDS),
                "deleted_ids": list(DELETE_IDS),
                "inactive_column_available": False,
                "masters_before": masters_before,
                "duplicate_links_before": links_before,
                "duplicate_links_after": links_after,
                "conflict_link_before": conflict_before,
                "conflict_link_after": conflict_after,
                "retained_after": retained_after,
                "protected_evidence_before": evidence_before,
                "protected_evidence_after": evidence_after,
            }
        connection.commit()
        return audit
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    print(json.dumps(apply_cleanup(), indent=2, default=str))
