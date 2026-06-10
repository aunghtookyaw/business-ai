import argparse
import json
from pathlib import Path
import sys

import psycopg2.extras
from psycopg2 import sql

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
from tools.formula_engine import _connect
from tools.master_data import duplicate_groups


MDM_SOURCES = {
    "categories": {
        "label": "Categories",
        "table": config.TRANSACTION_TABLE,
        "column": "Categorization",
    },
    "customers": {
        "label": "Customers",
        "table": config.SOTEPHWAR_TRANSECTION_TABLE,
        "column": "Customer_Name",
    },
}


def _source_rows(connection, table, column):
    query = sql.SQL(
        """
        SELECT {column} AS value, COUNT(*) AS row_count
        FROM {schema}.{table}
        WHERE COALESCE(__nc_deleted, false) = false
          AND NULLIF(TRIM({column}), '') IS NOT NULL
        GROUP BY {column}
        ORDER BY {column}
        """
    ).format(
        schema=sql.Identifier(config.TRANSACTION_SCHEMA),
        table=sql.Identifier(table),
        column=sql.Identifier(column),
    )
    with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute(query)
        return [dict(row) for row in cursor.fetchall()]


def analyze_sources(selected=None):
    selected = selected or tuple(MDM_SOURCES)
    report = {}
    with _connect() as connection:
        for source_key in selected:
            source = MDM_SOURCES[source_key]
            rows = _source_rows(connection, source["table"], source["column"])
            groups = duplicate_groups(rows)
            report[source_key] = {
                "label": source["label"],
                "table": source["table"],
                "column": source["column"],
                "distinct_values": len(rows),
                "duplicate_groups": [group.to_dict() for group in groups],
            }
    return report


def _print_text(report, limit):
    for source_key, source_report in report.items():
        print(f"{source_report['label']} ({source_report['table']}.{source_report['column']})")
        print(f"Distinct values: {source_report['distinct_values']}")
        print(f"Duplicate groups: {len(source_report['duplicate_groups'])}")
        groups = source_report["duplicate_groups"][:limit] if limit else source_report["duplicate_groups"]
        if not groups:
            print("No normalized duplicates found.")
            print()
            continue
        for group in groups:
            print()
            print(f"Canonical Value: {group['canonical_value']}")
            print(f"Normalized Name: {group['normalized_name']}")
            print(f"Total Rows: {group['total_rows']}")
            print("Possible Duplicates:")
            for variant in group["variants"]:
                print(f"- {variant['value']} ({variant['row_count']} rows)")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Read-only duplicate analysis for category/customer master data."
    )
    parser.add_argument(
        "source",
        nargs="*",
        help="Optional source(s) to scan: categories, customers. Defaults to both.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit duplicate groups per source in text output. 0 means no limit.",
    )
    args = parser.parse_args()

    invalid = sorted(set(args.source) - set(MDM_SOURCES))
    if invalid:
        parser.error("invalid source(s): " + ", ".join(invalid))

    report = analyze_sources(tuple(args.source) if args.source else None)
    if args.format == "json":
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        _print_text(report, args.limit)


if __name__ == "__main__":
    main()
