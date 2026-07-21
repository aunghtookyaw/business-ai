#!/usr/bin/env python3
"""Safely dry-run/apply the cleaned customer workbook to NocoDB customer_master."""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET

import psycopg2
import psycopg2.extras
from psycopg2 import sql

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config


NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_NS = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}
OFFICE_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PROTECTED_COLUMNS = {
    "id", "created_at", "updated_at", "created_by", "updated_by",
    "nc_order", "__nc_deleted", "nc_row_meta",
}


def clean_text(value):
    if value is None:
        return None
    value = re.sub(r"\s+", " ", str(value).strip())
    return value or None


def normalized_name(value):
    value = clean_text(value)
    return value.casefold() if value else None


def normalized_header(value):
    return re.sub(r"[^a-z0-9]+", "", (clean_text(value) or "").casefold())


def column_index(cell_ref):
    letters = re.match(r"[A-Z]+", cell_ref).group(0)
    result = 0
    for letter in letters:
        result = result * 26 + ord(letter) - 64
    return result - 1


def read_ready_sheet(path: Path):
    with zipfile.ZipFile(path) as archive:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        targets = {node.attrib["Id"]: node.attrib["Target"].lstrip("/") for node in relationships}
        sheet_path = None
        sheet_names = []
        for sheet in workbook.find("x:sheets", NS):
            name = sheet.attrib["name"]
            sheet_names.append(name)
            if name == "Ready for Import":
                rel_id = sheet.attrib[f"{{{OFFICE_REL}}}id"]
                sheet_path = targets[rel_id]
        if sheet_path is None:
            raise RuntimeError("Required worksheet 'Ready for Import' was not found")
        root = ET.fromstring(archive.read(sheet_path))
        parsed = []
        for row in root.findall(".//x:sheetData/x:row", NS):
            values = {}
            for cell in row.findall("x:c", NS):
                idx = column_index(cell.attrib["r"])
                node = cell.find("x:v", NS)
                values[idx] = clean_text(node.text if node is not None else None)
            parsed.append(values)
    if not parsed:
        raise RuntimeError("Ready for Import is empty")
    max_col = max(parsed[0], default=-1)
    headers = [parsed[0].get(index) for index in range(max_col + 1)]
    rows = []
    for excel_row, values in enumerate(parsed[1:], start=2):
        rows.append({"excel_row": excel_row, **{headers[i]: values.get(i) for i in range(len(headers))}})
    return sheet_names, headers, rows


def connect():
    return psycopg2.connect(
        host=config.POSTGRES_HOST,
        port=config.POSTGRES_PORT,
        dbname=config.POSTGRES_DB,
        user=config.POSTGRES_USER,
        password=config.POSTGRES_PASSWORD,
        connect_timeout=config.POSTGRES_CONNECT_TIMEOUT_SECONDS,
        options=f"-c statement_timeout={config.POSTGRES_STATEMENT_TIMEOUT_MS}",
    )


def detect_target(cursor):
    cursor.execute(
        """
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_type='BASE TABLE' AND lower(table_name)='customer_master'
          AND table_schema NOT IN ('pg_catalog','information_schema')
        ORDER BY table_schema
        """
    )
    targets = cursor.fetchall()
    if len(targets) != 1:
        raise RuntimeError(f"Expected exactly one customer_master target; found {targets!r}")
    first = targets[0]
    if isinstance(first, dict):
        schema, table = first["table_schema"], first["table_name"]
    else:
        schema, table = first
    cursor.execute(
        """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema=%s AND table_name=%s
        ORDER BY ordinal_position
        """,
        (schema, table),
    )
    column_rows = cursor.fetchall()
    columns = [
        (row["column_name"], row["data_type"]) if isinstance(row, dict) else tuple(row)
        for row in column_rows
    ]
    return schema, table, columns


def build_mapping(headers, columns):
    source = {normalized_header(header): header for header in headers if header}
    target = {normalized_header(name): name for name, _ in columns if name not in PROTECTED_COLUMNS}
    aliases = {
        "customername": ("customername",),
        "region": ("region",),
        "phonenumber": ("phonenumber", "phone", "mobile"),
        "town": ("town", "township", "address"),
        "customergroup": ("customergroup", "group", "customersegment"),
        "paymenttermsdays": ("paymenttermsdays", "paymentterms"),
        "active": ("active", "isactive", "status"),
        "notes": ("notes", "note"),
        "customercode": ("customercode",),
    }
    mapping = {}
    for source_key, candidates in aliases.items():
        if source_key not in source:
            continue
        for candidate in candidates:
            if candidate in target:
                mapping[source[source_key]] = target[candidate]
                break
    name_source = source.get("customername")
    name_target = target.get("customername")
    if not name_source or not name_target:
        raise RuntimeError("Customer Name source/target mapping is unavailable")
    return mapping, name_source, name_target


def load_existing(cursor, schema, table, columns, lock=False):
    business = [name for name, _ in columns if name not in PROTECTED_COLUMNS]
    query = sql.SQL("SELECT {} FROM {}.{} WHERE COALESCE(__nc_deleted,false)=false").format(
        sql.SQL(",").join(map(sql.Identifier, ["id", *business])),
        sql.Identifier(schema), sql.Identifier(table),
    )
    if lock:
        query += sql.SQL(" FOR UPDATE")
    cursor.execute(query)
    return [dict(row) for row in cursor.fetchall()]


def make_plan(rows, existing, mapping, name_source, name_target):
    database_by_name = defaultdict(list)
    for record in existing:
        database_by_name[normalized_name(record.get(name_target))].append(record)
    workbook_names = defaultdict(list)
    for row in rows:
        workbook_names[normalized_name(row.get(name_source))].append(row)

    plan = {"matched": [], "new": [], "updates": [], "conflicts": [], "skipped": []}
    for row in rows:
        norm = normalized_name(row.get(name_source))
        if not norm:
            plan["skipped"].append({"excel_row": row["excel_row"], "reason": "blank customer name"})
            continue
        if len(workbook_names[norm]) > 1:
            plan["skipped"].append({
                "excel_row": row["excel_row"], "name": row.get(name_source),
                "reason": "duplicate normalized name within Ready for Import",
            })
            continue
        candidates = database_by_name.get(norm, [])
        if len(candidates) > 1:
            plan["skipped"].append({
                "excel_row": row["excel_row"], "name": row.get(name_source),
                "reason": "ambiguous duplicate normalized name in database",
                "customer_ids": [item["id"] for item in candidates],
            })
            continue
        values = {}
        for source_column, target_column in mapping.items():
            value = clean_text(row.get(source_column))
            if value is not None:
                values[target_column] = value
        values[name_target] = clean_text(row[name_source])
        if not candidates:
            plan["new"].append({"excel_row": row["excel_row"], "name": values[name_target], "values": values})
            continue
        current = candidates[0]
        plan["matched"].append({"excel_row": row["excel_row"], "customer_id": current["id"], "name": current[name_target]})
        changes = {}
        for target_column, excel_value in values.items():
            if target_column == name_target:
                continue
            db_value = clean_text(current.get(target_column))
            if db_value is None:
                changes[target_column] = excel_value
            elif db_value.casefold() != excel_value.casefold():
                plan["conflicts"].append({
                    "excel_row": row["excel_row"], "customer_id": current["id"],
                    "name": current[name_target], "field": target_column,
                    "database_value": db_value, "excel_value": excel_value,
                })
        if changes:
            plan["updates"].append({"excel_row": row["excel_row"], "customer_id": current["id"], "name": current[name_target], "fields": changes})
    return plan


def counts(plan):
    return {
        "worksheet_rows": sum(len(plan[key]) for key in ("new", "skipped")) + len(plan["matched"]),
        "matched": len(plan["matched"]), "inserted": len(plan["new"]),
        "updated": len(plan["updates"]), "skipped": len(plan["skipped"]),
        "conflicts": len(plan["conflicts"]),
    }


def markdown_report(metadata, plan, applied=False, inserted_ids=None):
    tally = counts(plan)
    lines = [
        "# Customer Master Workbook Import Report", "",
        f"- Mode: **{'APPLIED' if applied else 'DRY RUN'}**",
        f"- Generated: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"- Workbook: `{metadata['workbook']}`", "- Worksheet used: `Ready for Import`",
        f"- Worksheets excluded: `{', '.join(metadata['excluded_sheets'])}`",
        f"- Target: `{metadata['database']}.{metadata['schema']}.{metadata['table']}`",
        f"- Actual columns: `{', '.join(metadata['columns'])}`",
        f"- Applied mapping: `{json.dumps(metadata['mapping'], ensure_ascii=False)}`",
        f"- Unmapped source fields (target absent, not imported): `{', '.join(metadata['unmapped_source_fields']) or 'None'}`",
        "", "## Counts", "",
        f"- Worksheet rows: {len(metadata['source_rows'])}", f"- Matched: {tally['matched']}",
        f"- New / inserted: {tally['inserted']}", f"- Existing records updated: {tally['updated']}",
        f"- Skipped: {tally['skipped']}", f"- Field conflicts preserved: {tally['conflicts']}", "",
    ]
    for title, key in (("Matched customers", "matched"), ("New customers", "new"), ("Fields to update", "updates"), ("Conflicts (database value preserved)", "conflicts"), ("Skipped rows", "skipped")):
        lines += [f"## {title}", ""]
        if not plan[key]:
            lines += ["None.", ""]
        else:
            lines += ["```json", json.dumps(plan[key], ensure_ascii=False, indent=2, default=str), "```", ""]
    if applied:
        lines += ["## Inserted Customer IDs", "", "```json", json.dumps(inserted_ids or [], ensure_ascii=False, indent=2), "```", ""]
    return "\n".join(lines)


def apply_plan(cursor, schema, table, plan):
    for update in plan["updates"]:
        fields = update["fields"]
        assignments = sql.SQL(",").join(sql.SQL("{}=%s").format(sql.Identifier(name)) for name in fields)
        query = sql.SQL("UPDATE {}.{} SET {} WHERE id=%s").format(sql.Identifier(schema), sql.Identifier(table), assignments)
        cursor.execute(query, [*fields.values(), update["customer_id"]])
        if cursor.rowcount != 1:
            raise RuntimeError(f"Update rowcount drift for customer {update['customer_id']}")
    inserted_ids = []
    for item in plan["new"]:
        values = item["values"]
        query = sql.SQL("INSERT INTO {}.{} ({}) VALUES ({}) RETURNING id").format(
            sql.Identifier(schema), sql.Identifier(table),
            sql.SQL(",").join(map(sql.Identifier, values)),
            sql.SQL(",").join(sql.Placeholder() for _ in values),
        )
        cursor.execute(query, list(values.values()))
        inserted_ids.append({"excel_row": item["excel_row"], "name": item["name"], "customer_id": cursor.fetchone()[0]})
    return inserted_ids


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--json-report", type=Path, required=True)
    args = parser.parse_args()
    sheet_names, headers, rows = read_ready_sheet(args.workbook)
    with connect() as connection:
        if args.apply:
            connection.set_session(isolation_level="SERIALIZABLE", readonly=False, autocommit=False)
        else:
            connection.set_session(readonly=True, autocommit=False)
        with connection.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
            schema, table, columns = detect_target(cursor)
            mapping, name_source, name_target = build_mapping(headers, columns)
            existing = load_existing(cursor, schema, table, columns, lock=args.apply)
            plan = make_plan(rows, existing, mapping, name_source, name_target)
            inserted_ids = apply_plan(cursor, schema, table, plan) if args.apply else []
            metadata = {
                "workbook": str(args.workbook), "database": config.POSTGRES_DB,
                "schema": schema, "table": table, "columns": [name for name, _ in columns],
                "mapping": mapping, "source_rows": [row["excel_row"] for row in rows],
                "excluded_sheets": [name for name in sheet_names if name != "Ready for Import"],
                "unmapped_source_fields": [header for header in headers if header not in mapping],
            }
            output = {"metadata": metadata, "counts": counts(plan), "plan": plan, "inserted_ids": inserted_ids, "applied": args.apply}
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(markdown_report(metadata, plan, args.apply, inserted_ids), encoding="utf-8")
            args.json_report.write_text(json.dumps(output, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            print(json.dumps({"target": f"{config.POSTGRES_DB}.{schema}.{table}", "counts": counts(plan), "mapping": mapping, "report": str(args.report)}, ensure_ascii=False))
            if not args.apply:
                connection.rollback()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
