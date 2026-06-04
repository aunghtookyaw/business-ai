import os
from datetime import timedelta

import config
from tools.formula_engine import _fetch_all, _financial_obligations_table_ref


SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


def _google_imports():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise RuntimeError(
            "Google Calendar libraries are not installed. Run: "
            "python3 -m pip install -r requirements.txt"
        ) from exc
    return Request, Credentials, InstalledAppFlow, build


def _reminder_minutes():
    return [
        int(item.strip())
        for item in config.GOOGLE_CALENDAR_REMINDER_MINUTES.split(",")
        if item.strip()
    ]


def _event_id(obligation_id):
    return f"bigshotobl{int(obligation_id)}"


def _credentials():
    Request, Credentials, InstalledAppFlow, _build = _google_imports()
    token_file = config.GOOGLE_CALENDAR_TOKEN_FILE
    credentials_file = config.GOOGLE_CALENDAR_CREDENTIALS_FILE
    creds = None

    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())

    if not creds or not creds.valid:
        if not os.path.exists(credentials_file):
            raise RuntimeError(
                f"Missing {credentials_file}. Download OAuth Desktop credentials "
                "from Google Cloud Console for bigshotagribusiness@gmail.com."
            )
        flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
        creds = flow.run_local_server(port=0, open_browser=False)

    with open(token_file, "w") as token:
        token.write(creds.to_json())

    return creds


def calendar_service():
    _Request, _Credentials, _InstalledAppFlow, build = _google_imports()
    return build("calendar", "v3", credentials=_credentials())


def active_obligations():
    return _fetch_all(
        f'''
        SELECT
          id,
          COALESCE("Category", '') AS category,
          COALESCE("Subcategory", '') AS subcategory,
          COALESCE("Creditor", '') AS creditor,
          COALESCE("Amount", 0) AS amount,
          COALESCE("Frequency", '') AS frequency,
          "Start_Date" AS start_date,
          "Next_Due_Date" AS next_due_date,
          COALESCE("Status", '') AS status,
          COALESCE("Notes", '') AS notes
        FROM {_financial_obligations_table_ref()}
        WHERE COALESCE("__nc_deleted", false) = false
          AND "Next_Due_Date" IS NOT NULL
          AND "Status" ILIKE 'Active'
        ORDER BY "Next_Due_Date", id
        '''
    )


def _event_body(row):
    amount = int(row.get("amount") or 0)
    due_date = row["next_due_date"].isoformat()
    end_date = (row["next_due_date"] + timedelta(days=1)).isoformat()
    reminders = [
        {"method": "popup", "minutes": minutes}
        for minutes in _reminder_minutes()
    ]
    summary = f"Pay: {row.get('creditor') or 'Financial obligation'} - {amount:,}"
    description = "\n".join([
        "BigShot financial obligation reminder",
        f"Creditor: {row.get('creditor') or '-'}",
        f"Amount: {amount:,}",
        f"Category: {row.get('category') or '-'}",
        f"Subcategory: {row.get('subcategory') or '-'}",
        f"Frequency: {row.get('frequency') or '-'}",
        f"Status: {row.get('status') or '-'}",
        f"Notes: {row.get('notes') or '-'}",
        f"Financial_Obligations id: {row['id']}",
    ])
    return {
        "id": _event_id(row["id"]),
        "summary": summary,
        "description": description,
        "start": {
            "date": due_date,
            "timeZone": config.GOOGLE_CALENDAR_TIMEZONE,
        },
        "end": {
            "date": end_date,
            "timeZone": config.GOOGLE_CALENDAR_TIMEZONE,
        },
        "reminders": {
            "useDefault": False,
            "overrides": reminders,
        },
        "extendedProperties": {
            "private": {
                "source": "business-ai",
                "financial_obligation_id": str(row["id"]),
            },
        },
    }


def sync_financial_obligations_to_calendar():
    service = calendar_service()
    calendar_id = config.GOOGLE_CALENDAR_ID
    synced = []
    errors = []

    for row in active_obligations():
        body = _event_body(row)
        event_id = body["id"]
        try:
            event = service.events().update(
                calendarId=calendar_id,
                eventId=event_id,
                body=body,
            ).execute()
            action = "updated"
        except Exception:
            try:
                event = service.events().insert(
                    calendarId=calendar_id,
                    body=body,
                ).execute()
                action = "created"
            except Exception as exc:
                errors.append({
                    "obligation_id": row["id"],
                    "creditor": row.get("creditor"),
                    "error": str(exc),
                })
                continue

        synced.append({
            "obligation_id": row["id"],
            "creditor": row.get("creditor"),
            "next_due_date": row.get("next_due_date"),
            "amount": int(row.get("amount") or 0),
            "action": action,
            "html_link": event.get("htmlLink"),
        })

    return {
        "calendar_id": calendar_id,
        "synced": synced,
        "errors": errors,
    }
