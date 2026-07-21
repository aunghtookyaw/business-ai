#!/usr/bin/env python3
"""Add approved customer detail columns and populate blank values atomically."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import psycopg2.extras
from psycopg2 import sql

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.import_customer_master_workbook import (  # noqa: E402
    clean_text,
    connect,
    detect_target,
    normalized_name,
    read_ready_sheet,
)


EXPECTED_SCHEMA = "pipkgfu2wr9qxyy"
ADDITIVE_COLUMNS = {
    "phone_number": "TEXT",
    "town": "TEXT",
    "customer_group": "TEXT",
    "payment_terms_days": "INTEGER",
    "active": "BOOLEAN",
    "notes": "TEXT",
    "contact_address": "TEXT",
}
SOURCE_MAP = {
    "Phone Number": "phone_number",
    "Town": "town",
    "Region": "Region",
    "Customer Group": "customer_group",
    "Payment Terms Days": "payment_terms_days",
    "Active": "active",
    "Notes": "notes",
}


def convert_value(target, value):
    value = clean_text(value)
    if value is None:
        return None
    if target == "payment_terms_days":
        number = float(value)
        if not number.is_integer():
            raise ValueError(f"Payment Terms Days is not an integer: {value!r}")
        return int(number)
    if target == "active":
        lowered = value.casefold()
        if lowered in {"yes", "true", "1"}:
            return True
        if lowered in {"no", "false", "0"}:
            return False
        raise ValueError(f"Unsupported Active value: {value!r}")
    if target == "customer_group":
        normalized = value.casefold().replace(" ", "")
        groups = {"farm": "Farm", "sotephwar": "SotePhwar", "both": "Both"}
        if normalized not in groups:
            raise ValueError(f"Unsupported Customer Group: {value!r}")
        return groups[normalized]
    return value


def is_blank(value):
    return value is None or (isinstance(value, str) and not value.strip())


def equivalent(left, right):
    if isinstance(left, str) and isinstance(right, str):
        return clean_text(left).casefold() == clean_text(right).casefold()
    return left == right


def build_plan(rows, records):
    by_name = defaultdict(list)
    for record in records:
        by_name[normalized_name(record["customer_name"])].append(record)
    plan = {"matched": [], "updates": [], "conflicts": [], "unmatched": []}
    for row in rows:
        name = clean_text(row["Customer Name"])
        matches = by_name.get(normalized_name(name), [])
        if len(matches) != 1:
            plan["unmatched"].append({
                "excel_row": row["excel_row"], "name": name,
                "reason": "not found" if not matches else "ambiguous database match",
                "customer_ids": [item["id"] for item in matches],
            })
            continue
        record = matches[0]
        plan["matched"].append({"excel_row": row["excel_row"], "customer_id": record["id"], "name": record["customer_name"]})
        changes = {}
        for source, target in SOURCE_MAP.items():
            excel_value = convert_value(target, row.get(source))
            if excel_value is None:
                continue
            database_value = record.get(target)
            if is_blank(database_value):
                changes[target] = excel_value
            elif not equivalent(database_value, excel_value):
                plan["conflicts"].append({
                    "excel_row": row["excel_row"], "customer_id": record["id"],
                    "name": record["customer_name"], "field": target,
                    "database_value": database_value, "excel_value": excel_value,
                })
        if changes:
            plan["updates"].append({"customer_id": record["id"], "name": record["customer_name"], "fields": changes})
    return plan


def write_report(path, metadata, plan, verification):
    lines = [
        "# Customer Master Additive Migration Report", "",
        f"- Applied: **{metadata['applied']}**",
        f"- Generated: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"- Target: `{metadata['database']}.{metadata['schema']}.{metadata['table']}`",
        f"- Worksheet: `Ready for Import` ({metadata['worksheet_rows']} rows)",
        f"- Added columns: `{', '.join(metadata['added_columns']) or 'None (already present)'}`",
        f"- Existing columns reused: `customer_name`, `Region`", "",
        "## Results", "",
        f"- Matched rows: {len(plan['matched'])}",
        f"- Updated rows: {len(plan['updates'])}",
        f"- Conflicts: {len(plan['conflicts'])}",
        f"- Unmatched rows: {len(plan['unmatched'])}",
        f"- Phone numbers beginning with zero: {verification.get('phones_beginning_zero', 0)}",
        f"- Blank phone numbers: {verification.get('blank_phones', 0)}", "",
        "## Customer-group totals", "",
    ]
    for group, count in sorted(verification.get("customer_group_totals", {}).items()):
        lines.append(f"- {group}: {count}")
    for title, key in (("Conflicts (preserved)", "conflicts"), ("Unmatched rows", "unmatched")):
        lines += ["", f"## {title}", "", "```json", json.dumps(plan[key], ensure_ascii=False, indent=2, default=str), "```"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--json-report", type=Path, required=True)
    args = parser.parse_args()
    sheets, headers, rows = read_ready_sheet(args.workbook)
    if "Manual Review" not in sheets or len(rows) != 293:
        raise RuntimeError("Workbook contract mismatch")
    with connect() as connection:
        connection.set_session(isolation_level="SERIALIZABLE", readonly=not args.apply, autocommit=False)
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            schema, table, original_columns = detect_target(cursor)
            if schema != EXPECTED_SCHEMA:
                raise RuntimeError(f"Detected schema {schema!r}, expected live schema {EXPECTED_SCHEMA!r}")
            original_names = {name for name, _ in original_columns}
            added = [name for name in ADDITIVE_COLUMNS if name not in original_names]
            if args.apply:
                for name in added:
                    cursor.execute(
                        sql.SQL("ALTER TABLE {}.{} ADD COLUMN {} {}").format(
                            sql.Identifier(schema), sql.Identifier(table), sql.Identifier(name), sql.SQL(ADDITIVE_COLUMNS[name])
                        )
                    )
            select_columns = ["id", "customer_name", "Region", *[name for name in ADDITIVE_COLUMNS if args.apply or name in original_names]]
            cursor.execute(
                sql.SQL("SELECT {} FROM {}.{} WHERE COALESCE(__nc_deleted,false)=false{}").format(
                    sql.SQL(",").join(map(sql.Identifier, select_columns)), sql.Identifier(schema), sql.Identifier(table)
                    , sql.SQL(" FOR UPDATE") if args.apply else sql.SQL("")
                )
            )
            records = cursor.fetchall()
            for record in records:
                for name in ADDITIVE_COLUMNS:
                    record.setdefault(name, None)
            plan = build_plan(rows, records)
            if len(plan["matched"]) != 293 or plan["unmatched"]:
                raise RuntimeError(f"Expected 293 unique matches; got {len(plan['matched'])}, unmatched={len(plan['unmatched'])}")
            if args.apply:
                for update in plan["updates"]:
                    fields = update["fields"]
                    cursor.execute(
                        sql.SQL("UPDATE {}.{} SET {} WHERE id=%s").format(
                            sql.Identifier(schema), sql.Identifier(table),
                            sql.SQL(",").join(sql.SQL("{}=%s").format(sql.Identifier(name)) for name in fields),
                        ),
                        [*fields.values(), update["customer_id"]],
                    )
                    if cursor.rowcount != 1:
                        raise RuntimeError(f"Update rowcount drift for ID {update['customer_id']}")
            if args.apply or "phone_number" in original_names:
                cursor.execute(
                    sql.SQL("SELECT COUNT(*) FILTER (WHERE left(phone_number,1)='0') AS phones_beginning_zero, "
                            "COUNT(*) FILTER (WHERE phone_number IS NULL OR btrim(phone_number)='') AS blank_phones "
                            "FROM {}.{} WHERE COALESCE(__nc_deleted,false)=false AND id = ANY(%s)").format(
                        sql.Identifier(schema), sql.Identifier(table)
                    ), ([item["customer_id"] for item in plan["matched"]],)
                )
                verification = dict(cursor.fetchone())
                cursor.execute(
                    sql.SQL("SELECT customer_group,COUNT(*) FROM {}.{} WHERE COALESCE(__nc_deleted,false)=false "
                            "AND id = ANY(%s) GROUP BY customer_group ORDER BY customer_group").format(
                        sql.Identifier(schema), sql.Identifier(table)
                    ), ([item["customer_id"] for item in plan["matched"]],)
                )
                verification["customer_group_totals"] = {row["customer_group"] or "Blank": row["count"] for row in cursor.fetchall()}
            else:
                phone_values = [convert_value("phone_number", row.get("Phone Number")) for row in rows]
                verification = {
                    "phones_beginning_zero": sum(bool(value and value.startswith("0")) for value in phone_values),
                    "blank_phones": sum(value is None for value in phone_values),
                    "customer_group_totals": dict(Counter(convert_value("customer_group", row.get("Customer Group")) for row in rows)),
                }
            metadata = {
                "applied": args.apply, "database": "automationdb", "schema": schema, "table": table,
                "worksheet_rows": len(rows), "added_columns": added, "headers": headers,
            }
            output = {"metadata": metadata, "counts": {
                "matched": len(plan["matched"]), "updated": len(plan["updates"]),
                "conflicts": len(plan["conflicts"]), "unmatched": len(plan["unmatched"]), "inserted": 0,
            }, "verification": verification, "plan": plan}
            write_report(args.report, metadata, plan, verification)
            args.json_report.write_text(json.dumps(output, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            print(json.dumps({"counts": output["counts"], "added_columns": added, "verification": verification, "report": str(args.report)}, ensure_ascii=False))
            if not args.apply:
                connection.rollback()


if __name__ == "__main__":
    main()
