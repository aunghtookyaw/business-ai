#!/usr/bin/env python3
"""Apply or roll back the versioned Veggies Production schema migration."""

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.formula_engine import _connect


MIGRATION = PROJECT_ROOT / "migrations" / "20260714_001_veggies_production_up.sql"
ROLLBACK = PROJECT_ROOT / "migrations" / "20260714_001_veggies_production_down.sql"


def run_migration(direction="up", connection=None):
    path = MIGRATION if direction == "up" else ROLLBACK
    sql = path.read_text(encoding="utf-8")
    owns_connection = connection is None
    connection = connection or _connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        if owns_connection:
            connection.close()
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("direction", choices=("up", "down"), nargs="?", default="up")
    args = parser.parse_args()
    path = run_migration(args.direction)
    print(f"Applied {args.direction} migration: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
