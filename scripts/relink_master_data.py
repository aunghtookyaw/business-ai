import argparse
import csv
from datetime import datetime
import json
from pathlib import Path
import sys

import psycopg2.extras
from psycopg2 import sql

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
from tools.formula_engine import _connect
from tools.master_relink import filter_plan_to_transaction_ids, plan_relinks
from tools.master_relink_db import RELINK_TARGETS


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKUP_DIR = PROJECT_ROOT.parent / "backups"


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
    if not _table_exists(connection, target["junction_table"]):
        raise RuntimeError(f'Junction table not found: {target["junction_table"]}')
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


def _table_exists(connection, table_name):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = %s
              AND table_name = %s
            """,
            (config.TRANSACTION_SCHEMA, table_name),
        )
        return cursor.fetchone() is not None


def _backup_links(connection, selected):
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"master_relink_backup_{timestamp}.json"
    payload = {}
    for target_key in selected:
        target = RELINK_TARGETS[target_key]
        payload[target_key] = {
            "junction_table": target["junction_table"],
            "links": _fetch_existing_links(connection, target),
        }
    backup_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return backup_path


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


def _replace_conflicting_links(connection, target, conflicts):
    if not conflicts:
        return 0

    transaction_ids = [int(conflict["transaction_id"]) for conflict in conflicts]
    delete_query = sql.SQL(
        """
        DELETE FROM {schema}.{table}
        WHERE {transaction_column} = ANY(%s)
        """
    ).format(
        schema=sql.Identifier(config.TRANSACTION_SCHEMA),
        table=sql.Identifier(target["junction_table"]),
        transaction_column=sql.Identifier(target["junction_transaction_column"]),
    )
    insert_pairs = [
        (int(conflict["transaction_id"]), int(conflict["target_master_id"]))
        for conflict in conflicts
    ]
    with connection.cursor() as cursor:
        cursor.execute(delete_query, (transaction_ids,))
    return _insert_links(connection, target, insert_pairs)


def _write_unmatched_csv(report):
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = BACKUP_DIR / f"master_relink_unmatched_{timestamp}.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["target", "value", "row_count"])
        writer.writeheader()
        for target_key, target_report in report.items():
            for row in target_report["unmatched_values"]:
                writer.writerow({
                    "target": target_key,
                    "value": row["value"],
                    "row_count": row["row_count"],
                })
    return path


def relink_master_data(selected=None, apply=False, transaction_ids_by_target=None, replace_conflicts=False):
    selected = selected or tuple(RELINK_TARGETS)
    transaction_ids_by_target = transaction_ids_by_target or {}
    report = {}
    backup_path = None
    with _connect() as connection:
        if apply:
            backup_path = _backup_links(connection, selected)
        for target_key in selected:
            target = RELINK_TARGETS[target_key]
            plan = plan_relinks(
                _fetch_transaction_rows(connection, target),
                _fetch_master_rows(connection, target),
                _fetch_existing_links(connection, target),
            )
            if target_key in transaction_ids_by_target:
                plan = filter_plan_to_transaction_ids(
                    plan,
                    transaction_ids_by_target[target_key],
                )
            inserted = 0
            replaced = 0
            if apply:
                if plan.duplicate_master_names:
                    raise RuntimeError(f"{target_key} has duplicate normalized master names")
                if plan.conflicts and not replace_conflicts:
                    raise RuntimeError(
                        f"{target_key} has {len(plan.conflicts)} conflicting existing links; "
                        "rerun with --replace-conflicts to replace them"
                    )
                inserted = _insert_links(connection, target, plan.to_insert)
                if replace_conflicts:
                    replaced = _replace_conflicting_links(connection, target, plan.conflicts)
            report[target_key] = {
                "label": target["label"],
                "mode": "apply" if apply else "dry-run",
                "inserted": inserted,
                "replaced_conflicts": replaced,
                **plan.to_dict(),
            }
        if apply:
            connection.commit()
    unmatched_path = _write_unmatched_csv(report)
    return report, backup_path, unmatched_path


def _print_report(report, backup_path=None, unmatched_path=None):
    for target_key, target_report in report.items():
        print(f"{target_report['label']} ({target_key})")
        print(f"Mode: {target_report['mode']}")
        print(f"Total: {target_report['total']}")
        print(f"Matched: {target_report['matched']}")
        print(f"Unmatched: {target_report['unmatched']}")
        print(f"Blank: {target_report['blank']}")
        print(f"Already linked: {target_report['already_linked']}")
        print(f"Ready to insert: {target_report['to_insert']}")
        print(f"Inserted: {target_report['inserted']}")
        print(f"Replaced conflicts: {target_report.get('replaced_conflicts', 0)}")
        print(f"Conflicts skipped: {len(target_report['conflicts'])}")
        if target_report["unmatched_values"]:
            print("Top unmatched values:")
            for row in target_report["unmatched_values"][:30]:
                print(f"- {row['value']} ({row['row_count']} rows)")
        if target_report["duplicate_master_names"]:
            print("Duplicate normalized master names:")
            for row in target_report["duplicate_master_names"]:
                print(f"- {row['normalized_name']}: {row['masters']}")
        print()
    if backup_path:
        print(f"Backup: {backup_path}")
    if unmatched_path:
        print(f"Unmatched report: {unmatched_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Relink existing transaction rows to existing category/customer master tables."
    )
    parser.add_argument("target", nargs="*", help="Optional target(s): categories, customers")
    parser.add_argument("--apply", action="store_true", help="Write missing links. Default is dry-run.")
    parser.add_argument(
        "--replace-conflicts",
        action="store_true",
        help="When applying, replace wrong existing links with the normalized master match.",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args()

    invalid = sorted(set(args.target) - set(RELINK_TARGETS))
    if invalid:
        parser.error("invalid target(s): " + ", ".join(invalid))

    report, backup_path, unmatched_path = relink_master_data(
        tuple(args.target) if args.target else None,
        apply=args.apply,
        replace_conflicts=args.replace_conflicts,
    )
    if args.format == "json":
        print(json.dumps({
            "report": report,
            "backup_path": str(backup_path) if backup_path else None,
            "unmatched_path": str(unmatched_path) if unmatched_path else None,
        }, indent=2, ensure_ascii=False))
    else:
        _print_report(report, backup_path=backup_path, unmatched_path=unmatched_path)


if __name__ == "__main__":
    main()
