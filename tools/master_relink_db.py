import psycopg2.extras
from psycopg2 import sql

import config
from tools.formula_engine import _connect
from tools.master_relink import filter_plan_to_transaction_ids, plan_relinks


RELINK_TARGETS = {
    "categories": {
        "label": "Transection categories",
        "transaction_table": config.TRANSACTION_TABLE,
        "transaction_column": "Categorization",
        "master_table": "category_master",
        "master_column": "category_name",
        "junction_table": "_nc_m2m_Transection_category_master",
        "junction_transaction_column": "Transection_id",
        "junction_master_column": "category_master_id",
    },
    "customers": {
        "label": "Sotephwar customers",
        "transaction_table": config.SOTEPHWAR_TRANSECTION_TABLE,
        "transaction_column": "Customer_Name",
        "master_table": "customer_master",
        "master_column": "customer_name",
        "junction_table": "_nc_m2m_Sotephwar_Trans_customer_master",
        "junction_transaction_column": "Sotephwar_Transection_id",
        "junction_master_column": "customer_master_id",
    },
}


def relink_inserted_rows(inserted_ids_by_table):
    transaction_ids_by_target = {}
    if inserted_ids_by_table.get("transection"):
        transaction_ids_by_target["categories"] = inserted_ids_by_table["transection"]
    if inserted_ids_by_table.get("sotephwar_transection"):
        transaction_ids_by_target["customers"] = inserted_ids_by_table["sotephwar_transection"]
    if not transaction_ids_by_target:
        return {}

    report = {}
    with _connect() as connection:
        for target_key, transaction_ids in transaction_ids_by_target.items():
            target = RELINK_TARGETS[target_key]
            plan = filter_plan_to_transaction_ids(
                plan_relinks(
                    _fetch_transaction_rows(connection, target),
                    _fetch_master_rows(connection, target),
                    _fetch_existing_links(connection, target),
                ),
                transaction_ids,
            )
            inserted = _insert_links(connection, target, plan.to_insert)
            report[target_key] = {
                "label": target["label"],
                "inserted": inserted,
                **plan.to_dict(),
            }
        connection.commit()
    return report


def _fetch_transaction_rows(connection, target):
    query = sql.SQL(
        """
        SELECT id, {value_column} AS value
        FROM {schema}.{table}
        WHERE COALESCE(__nc_deleted, false) = false
        ORDER BY id
        """
    ).format(
        schema=sql.Identifier(config.TRANSACTION_SCHEMA),
        table=sql.Identifier(target["transaction_table"]),
        value_column=sql.Identifier(target["transaction_column"]),
    )
    with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute(query)
        return [dict(row) for row in cursor.fetchall()]


def _fetch_master_rows(connection, target):
    query = sql.SQL(
        """
        SELECT id, {value_column} AS value
        FROM {schema}.{table}
        WHERE COALESCE(__nc_deleted, false) = false
          AND NULLIF(TRIM({value_column}), '') IS NOT NULL
        ORDER BY id
        """
    ).format(
        schema=sql.Identifier(config.TRANSACTION_SCHEMA),
        table=sql.Identifier(target["master_table"]),
        value_column=sql.Identifier(target["master_column"]),
    )
    with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute(query)
        return [dict(row) for row in cursor.fetchall()]


def _fetch_existing_links(connection, target):
    query = sql.SQL(
        """
        SELECT {transaction_column} AS transaction_id,
               {master_column} AS master_id
        FROM {schema}.{table}
        WHERE {transaction_column} IS NOT NULL
          AND {master_column} IS NOT NULL
        """
    ).format(
        schema=sql.Identifier(config.TRANSACTION_SCHEMA),
        table=sql.Identifier(target["junction_table"]),
        transaction_column=sql.Identifier(target["junction_transaction_column"]),
        master_column=sql.Identifier(target["junction_master_column"]),
    )
    with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute(query)
        return [dict(row) for row in cursor.fetchall()]


def _insert_links(connection, target, pairs):
    if not pairs:
        return 0
    query = sql.SQL(
        """
        INSERT INTO {schema}.{table}
          ({transaction_column}, {master_column})
        VALUES
          (%s, %s)
        """
    ).format(
        schema=sql.Identifier(config.TRANSACTION_SCHEMA),
        table=sql.Identifier(target["junction_table"]),
        transaction_column=sql.Identifier(target["junction_transaction_column"]),
        master_column=sql.Identifier(target["junction_master_column"]),
    )
    with connection.cursor() as cursor:
        cursor.executemany(query, pairs)
    return len(pairs)
