#!/usr/bin/env python3
"""Print the safe NocoDB configuration plan; optionally query table metadata.

The script deliberately never writes NocoDB's PostgreSQL metadata tables. Live
changes remain an administrator action in the NocoDB UI because metadata API
payloads vary by installed NocoDB version.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
METADATA_PATH = PROJECT_ROOT / "nocodb" / "veggies_production_metadata.json"


def load_plan(path: Path = METADATA_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def fetch_tables(base_url: str, base_id: str, token: str) -> dict:
    """Read current NocoDB metadata; this function never mutates NocoDB."""
    url = f"{base_url.rstrip('/')}/api/v2/meta/bases/{base_id}/tables"
    request = urllib.request.Request(url, headers={"xc-token": token, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inspect-live", action="store_true", help="Read current table metadata; makes no changes.")
    parser.add_argument("--base-url", default=os.getenv("NOCODB_URL", "http://127.0.0.1:8080"))
    parser.add_argument("--base-id", default=os.getenv("NOCODB_BASE_ID"))
    parser.add_argument("--token", default=os.getenv("NOCODB_TOKEN"))
    args = parser.parse_args()

    plan = load_plan()
    print(json.dumps(plan, indent=2))
    if not args.inspect_live:
        print("\nPlan only: no NocoDB API call was made.")
        return 0
    if not args.base_id or not args.token:
        parser.error("--inspect-live requires NOCODB_BASE_ID/--base-id and NOCODB_TOKEN/--token")
    try:
        current = fetch_tables(args.base_url, args.base_id, args.token)
    except urllib.error.HTTPError as exc:
        print(f"NocoDB metadata inspection failed: HTTP {exc.code}", file=sys.stderr)
        return 1
    print("\nCurrent NocoDB tables (read-only response):")
    print(json.dumps(current, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
