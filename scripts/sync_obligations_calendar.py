import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from tools.google_calendar_client import sync_financial_obligations_to_calendar


def main():
    try:
        result = sync_financial_obligations_to_calendar()
    except Exception as exc:
        print(f"Calendar sync error: {exc}")
        return 1

    print(f"Calendar: {result['calendar_id']}")
    print(f"Synced: {len(result['synced'])}")
    for row in result["synced"]:
        print(
            "{action}: {creditor} {amount:,} due {next_due_date}".format(
                action=row["action"],
                creditor=row["creditor"] or "-",
                amount=row["amount"],
                next_due_date=row["next_due_date"],
            )
        )
    if result["errors"]:
        print(f"Errors: {len(result['errors'])}")
        for error in result["errors"]:
            print(f"- {error['obligation_id']} {error['creditor']}: {error['error']}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
