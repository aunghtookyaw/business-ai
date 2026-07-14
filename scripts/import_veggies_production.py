#!/usr/bin/env python3
"""Preview or import a wide Veggies Production workbook."""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.veggies_production import (
    import_veggies_preview,
    load_crop_definitions,
    parse_veggies_workbook,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--apply", action="store_true", help="Insert valid rows after preview")
    parser.add_argument("--imported-by", default="command-line")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    preview = parse_veggies_workbook(args.workbook, load_crop_definitions())
    result = preview.as_dict(include_rows=False)
    if args.apply:
        result["import_result"] = import_veggies_preview(preview, args.imported_by)

    if args.as_json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(f"Workbook: {result['filename']}")
        print(f"Source rows: {result['total_source_rows']}")
        print(f"Accepted rows: {result['accepted_rows']}")
        print(f"Rejected rows: {result['rejected_rows']}")
        print(f"Normalized items: {result['normalized_items']}")
        print(f"Duplicate rows: {len(result['duplicate_rows'])}")
        for error in result["errors"]:
            print(f"Row {error['row_number']} [{error['column']}]: {error['message']}")
        if args.apply:
            print(json.dumps(result["import_result"], indent=2, default=str))
    return 1 if preview.errors and not preview.valid_rows else 0


if __name__ == "__main__":
    raise SystemExit(main())
