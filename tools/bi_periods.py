from datetime import date, timedelta


RELATIVE_PERIODS = [
    ("today", "Today"),
    ("yesterday", "Yesterday"),
    ("this_week", "This Week"),
    ("last_week", "Last Week"),
    ("this_month", "This Month"),
    ("last_month", "Last Month"),
    ("this_quarter", "This Quarter"),
    ("last_quarter", "Last Quarter"),
    ("this_year", "This Year"),
    ("last_year", "Last Year"),
]


def relative_period(value):
    return {"type": "relative", "value": value}


def month_period(year, month):
    return {"type": "month", "year": int(year), "month": int(month)}


def quarter_period(year, quarter):
    return {"type": "quarter", "year": int(year), "quarter": int(quarter)}


def date_period(value):
    return {"type": "date", "date": value}


def range_period(start, end):
    return {"type": "range", "start": start, "end": end}


def legacy_period(period):
    if not period:
        return "all_time"
    kind = period.get("type")
    if kind == "relative":
        return period.get("value") or "all_time"
    if kind == "month":
        return "month:{year}-{month:02d}".format(
            year=int(period["year"]),
            month=int(period["month"]),
        )
    if kind == "quarter":
        return "quarter:{year}-Q{quarter}".format(
            year=int(period["year"]),
            quarter=int(period["quarter"]),
        )
    if kind == "date":
        return f"date:{period['date']}"
    if kind == "range":
        return f"range:{period['start']}:{period['end']}"
    return "all_time"


def period_label(period):
    if not period:
        return "All time"
    kind = period.get("type")
    if kind == "relative":
        return dict(RELATIVE_PERIODS).get(period.get("value"), period.get("value", "All time"))
    if kind == "month":
        return date(int(period["year"]), int(period["month"]), 1).strftime("%B %Y")
    if kind == "quarter":
        return f"Q{int(period['quarter'])} {int(period['year'])}"
    if kind == "date":
        return period["date"]
    if kind == "range":
        return f"{period['start']} to {period['end']}"
    return "All time"


def month_days(year, month):
    start = date(int(year), int(month), 1)
    if start.month == 12:
        end = date(start.year + 1, 1, 1)
    else:
        end = date(start.year, start.month + 1, 1)
    days = []
    current = start
    while current < end:
        days.append(current)
        current += timedelta(days=1)
    return days
