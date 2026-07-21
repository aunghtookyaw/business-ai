"""Validated General Transaction workflow and atomic PostgreSQL persistence."""
from copy import deepcopy
from datetime import date
import json
from uuid import uuid4

import psycopg2.extras
from psycopg2 import sql

import config
from tools.formula_engine import _connect
from tools import draft_management


DRAFT_TABLE = "business_os_general_transaction_draft"
PAYMENT_METHODS = ("Cash", "KPay", "AYA Pay", "UAB Pay", "Other Online Pay")
TRANSACTION_TYPES = ("Income", "Expense")
SECTORS = ("Farm", "Sote Phwar")


class GeneralTransactionValidationError(ValueError):
    def __init__(self, errors):
        self.errors = errors
        super().__init__("; ".join(errors))


def _text(value):
    return str(value or "").strip()


def _draft_amount(value):
    """Keep incomplete operator input saveable so validation can explain it safely."""
    try:
        return int(str(value or "0").replace(",", "").strip())
    except (TypeError, ValueError):
        return 0


def validate(values, category=None):
    value = deepcopy(values or {})
    errors = []
    try:
        value["transaction_date"] = date.fromisoformat(_text(value.get("transaction_date"))).isoformat()
    except ValueError:
        errors.append("Transaction date must use YYYY-MM-DD")
    value["transaction_type"] = _text(value.get("transaction_type"))
    value["sector"] = _text(value.get("sector"))
    value["description"] = _text(value.get("description"))
    value["payment_method"] = _text(value.get("payment_method"))
    value["comment"] = _text(value.get("comment"))
    if value["transaction_type"] not in TRANSACTION_TYPES:
        errors.append("Type must be Income or Expense")
    if value["sector"] not in SECTORS:
        errors.append("Sector must be Farm or Sote Phwar")
    if not value["description"]:
        errors.append("Description is required")
    if value["payment_method"] not in PAYMENT_METHODS:
        errors.append("Payment method is required and must be Cash, KPay, AYA Pay, UAB Pay, or Other Online Pay")
    try:
        raw_amount = str(value.get("amount", "")).replace(",", "").strip()
        if not raw_amount or any(character in raw_amount for character in ".eE"):
            raise ValueError
        value["amount"] = int(raw_amount)
        if value["amount"] <= 0:
            raise ValueError
    except (TypeError, ValueError):
        errors.append("Amount must be a positive whole-number MMK amount")
    try:
        value["category_id"] = int(value.get("category_id"))
    except (TypeError, ValueError):
        errors.append("Category is required")
    if not category or not category.get("category_name"):
        errors.append("Category is inactive or unavailable")
    else:
        value["category_id"] = int(category["id"])
        value["category_name"] = category["category_name"]
        value["category_code"] = category.get("category_code") or ""
    if errors:
        raise GeneralTransactionValidationError(errors)
    return value


def _payload(row):
    if not row:
        return None
    value = dict(row)
    for key in ("transaction_date", "created_at", "updated_at", "submitted_at"):
        if value.get(key):
            value[key] = value[key].isoformat()
    if value.get("submission_key"):
        value["submission_key"] = str(value["submission_key"])
    value["amount"] = int(value.get("amount") or 0)
    return value


def _schema():
    return config.TRANSACTION_SCHEMA


def list_categories():
    with _connect() as connection, connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute(sql.SQL(
            'SELECT id,"Category_Code" AS category_code,category_name FROM {}.category_master '
            "WHERE COALESCE(__nc_deleted,false)=false AND NULLIF(TRIM(category_name),'') IS NOT NULL "
            'ORDER BY category_name,id'
        ).format(sql.Identifier(_schema())))
        return [dict(row) for row in cursor.fetchall()]


def _active_category(connection, category_id, lock=False):
    try:
        category_id = int(category_id)
    except (TypeError, ValueError):
        return None
    with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute(sql.SQL(
            'SELECT id,"Category_Code" AS category_code,category_name FROM {}.category_master '
            "WHERE id=%s AND COALESCE(__nc_deleted,false)=false AND NULLIF(TRIM(category_name),'') IS NOT NULL{}"
        ).format(sql.Identifier(_schema()), sql.SQL(" FOR SHARE" if lock else "")), (category_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def create_draft(values, created_by):
    values = values or {}
    # Bind UUID as canonical text for psycopg2 installations where the UUID
    # adapter is not globally registered; PostgreSQL validates the uuid column.
    key = str(uuid4())
    with _connect() as connection, connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute(sql.SQL(
            'INSERT INTO {}.{} (submission_key,transaction_date,transaction_type,sector,category_id,description,'
            'amount,payment_method,attachment_path,attachment_name,comment,created_by) '
            'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *'
        ).format(sql.Identifier(_schema()), sql.Identifier(DRAFT_TABLE)), (
            key, values.get("transaction_date") or date.today(), _text(values.get("transaction_type")),
            _text(values.get("sector")), values.get("category_id") or None, _text(values.get("description")),
            _draft_amount(values.get("amount")), _text(values.get("payment_method")),
            _text(values.get("attachment_path")), _text(values.get("attachment_name")),
            _text(values.get("comment")), created_by,
        ))
        row = cursor.fetchone(); connection.commit(); return _payload(row)


def get_draft(draft_id, connection=None, for_update=False):
    owns = connection is None; connection = connection or _connect()
    try:
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(sql.SQL('SELECT * FROM {}.{} WHERE id=%s AND is_deleted=false{}').format(
                sql.Identifier(_schema()), sql.Identifier(DRAFT_TABLE), sql.SQL(" FOR UPDATE" if for_update else "")
            ), (int(draft_id),))
            return _payload(cursor.fetchone())
    finally:
        if owns: connection.close()


def list_drafts(limit=50):
    with _connect() as connection, connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute(sql.SQL("SELECT d.*,cm.category_name,cm.\"Category_Code\" AS category_code FROM {}.{} d LEFT JOIN {}.category_master cm ON cm.id=d.category_id WHERE d.status<>'submitted' AND d.is_deleted=false ORDER BY d.updated_at DESC LIMIT %s").format(
            sql.Identifier(_schema()),sql.Identifier(DRAFT_TABLE),sql.Identifier(_schema())),(max(1,min(int(limit),100)),))
        return [_payload(row) for row in cursor.fetchall()]


def update_draft(draft_id, values, expected_version):
    current = get_draft(draft_id)
    if not current: raise LookupError("General Transaction draft not found")
    if current["status"] == "submitted": raise ValueError("Submitted General Transactions cannot be edited")
    merged = {**current, **(values or {})}
    with _connect() as connection, connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute(sql.SQL(
            'UPDATE {}.{} SET status=\'draft\',transaction_date=%s,transaction_type=%s,sector=%s,category_id=%s,'
            'description=%s,amount=%s,payment_method=%s,attachment_path=%s,attachment_name=%s,comment=%s,'
            'version=version+1,updated_at=now() WHERE id=%s AND version=%s AND status<>\'submitted\' RETURNING *'
        ).format(sql.Identifier(_schema()), sql.Identifier(DRAFT_TABLE)), (
            merged.get("transaction_date"), _text(merged.get("transaction_type")), _text(merged.get("sector")),
            merged.get("category_id") or None, _text(merged.get("description")), _draft_amount(merged.get("amount")),
            _text(merged.get("payment_method")), _text(merged.get("attachment_path")),
            _text(merged.get("attachment_name")), _text(merged.get("comment")), int(draft_id), int(expected_version),
        ))
        row = cursor.fetchone()
        if not row: raise RuntimeError("Draft is stale. Refresh and retry.")
        connection.commit(); return _payload(row)


def set_workflow_state(draft_id, state):
    if state != "validated": raise ValueError("General Transactions use Save Draft, Validate, then Confirm & Submit")
    with _connect() as connection:
        draft = get_draft(draft_id, connection, for_update=True)
        if not draft: raise LookupError("General Transaction draft not found")
        if draft["status"] == "submitted": raise ValueError("Submitted General Transactions cannot change")
        normalized = validate(draft, _active_category(connection, draft.get("category_id"), lock=True))
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(sql.SQL('UPDATE {}.{} SET status=%s,updated_at=now(),version=version+1 WHERE id=%s RETURNING *').format(
                sql.Identifier(_schema()), sql.Identifier(DRAFT_TABLE)), (state, int(draft_id)))
            row = cursor.fetchone()
        connection.commit(); return {"draft": _payload(row), "transaction": normalized}


def _reject_voucher_collision(connection, transaction):
    if transaction["transaction_type"] != "Income": return
    if transaction["sector"] == "Farm":
        table, date_column, amount_column, module = "farm_transection", "Date", "Total_Amount", "Farm Voucher"
    else:
        table, date_column, amount_column, module = "Sotephwar_Transection", "Invoice_Date", "Total_Amount", "SotePhwar Voucher"
    with connection.cursor() as cursor:
        cursor.execute(sql.SQL('SELECT 1 FROM {}.{} WHERE COALESCE(__nc_deleted,false)=false AND {}=%s AND COALESCE({},0)=%s LIMIT 1').format(
            sql.Identifier(_schema()), sql.Identifier(table), sql.Identifier(date_column), sql.Identifier(amount_column)
        ), (transaction["transaction_date"], transaction["amount"]))
        if cursor.fetchone():
            raise GeneralTransactionValidationError([f"Income matches an existing {module} sale by date and amount; use the {module} module"])


def submit(draft_id, submission_key, submitted_by, connection=None, commit=True):
    owns = connection is None; connection = connection or _connect()
    if owns: connection.set_session(isolation_level="SERIALIZABLE", autocommit=False)
    try:
        draft = get_draft(draft_id, connection, for_update=True)
        if not draft: raise LookupError("General Transaction draft not found")
        if str(draft["submission_key"]) != _text(submission_key): raise ValueError("Invalid submission identity")
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (f"GeneralTransaction|{submission_key}",))
        if draft["status"] == "submitted":
            if commit: connection.commit()
            return {"draft": draft, "transaction_id": draft["submitted_transaction_id"], "idempotent": True}
        # Historical previewed drafts remain submit-compatible, while the current
        # workflow proceeds directly from server-validated to submitted.
        if draft["status"] not in {"validated", "previewed"}:
            raise GeneralTransactionValidationError(["Draft must be validated before submission"])
        category = _active_category(connection, draft.get("category_id"), lock=True)
        transaction = validate(draft, category)
        _reject_voucher_collision(connection, transaction)
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(sql.SQL(
                'INSERT INTO {}."Transection" ("Date","Income_Expense","Categorization","Sector","Item_Description",'
                '"Amount","Payment_Method","Attachement","AI_Comment") VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id'
            ).format(sql.Identifier(_schema())), (
                transaction["transaction_date"], transaction["transaction_type"], category["category_name"],
                transaction["sector"], transaction["description"], transaction["amount"],
                transaction["payment_method"], draft.get("attachment_path") or None, transaction["comment"] or None,
            ))
            transaction_id = int(cursor.fetchone()["id"])
            cursor.execute(sql.SQL(
                'INSERT INTO {}."_nc_m2m_Transection_category_master" ("Transection_id",category_master_id) VALUES (%s,%s)'
            ).format(sql.Identifier(_schema())), (transaction_id, int(category["id"])))
            submitted = {**transaction, "transaction_id": transaction_id, "submitted_by": submitted_by}
            cursor.execute(sql.SQL(
                'UPDATE {}.{} SET status=\'submitted\',submitted_transaction_id=%s,submitted_json=%s::jsonb,'
                'submitted_at=now(),updated_at=now(),version=version+1 WHERE id=%s RETURNING *'
            ).format(sql.Identifier(_schema()), sql.Identifier(DRAFT_TABLE)),
            (transaction_id, json.dumps(submitted), int(draft_id)))
            saved = cursor.fetchone()
        if commit: connection.commit()
        return {"draft": _payload(saved), "transaction_id": transaction_id, "idempotent": False}
    except Exception:
        connection.rollback(); raise
    finally:
        if owns: connection.close()


def recent_transactions(filters=None, page=1, page_size=20):
    filters = filters or {}; clauses = []; page,page_size,offset=draft_management.paging(page,page_size); params = {"limit":page_size,"offset":offset}
    mapping = {"date_from": 't."Date">=%(date_from)s', "date_to": 't."Date"<=%(date_to)s',
               "transaction_type": 't."Income_Expense"=%(transaction_type)s', "sector": 't."Sector"=%(sector)s',
               "category_id": 'l.category_master_id=%(category_id)s'}
    for key, clause in mapping.items():
        if filters.get(key): clauses.append(clause); params[key] = filters[key]
    where = " AND ".join(["d.status='submitted'","d.is_deleted=false"] + clauses)
    with _connect() as connection, connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute(sql.SQL('SELECT t.id,t."Date" AS transaction_date,t."Income_Expense" AS transaction_type,'
            't."Sector" AS sector,COALESCE(cm.category_name,t."Categorization") AS category_name,t."Item_Description" AS description,t."Amount" AS amount,'
            't."Payment_Method" AS payment_method,d.submitted_at,t."Attachement" AS attachment,d.id AS draft_id,COUNT(*) OVER() total_count FROM {}.{} d JOIN {}."Transection" t ON t.id=d.submitted_transaction_id '
            'JOIN {}."_nc_m2m_Transection_category_master" l ON l."Transection_id"=t.id '
            'LEFT JOIN {}.category_master cm ON cm.id=l.category_master_id WHERE '+where+' ORDER BY d.submitted_at DESC,t.id DESC LIMIT %(limit)s OFFSET %(offset)s').format(
                sql.Identifier(_schema()), sql.Identifier(DRAFT_TABLE), sql.Identifier(_schema()), sql.Identifier(_schema()), sql.Identifier(_schema())
            ), params)
        rows = [dict(row) for row in cursor.fetchall()]
    total=int(rows[0].pop("total_count")) if rows else 0
    for row in rows:
        row["transaction_date"] = row["transaction_date"].isoformat(); row["amount"] = int(row["amount"] or 0); row["submitted_at"]=row["submitted_at"].isoformat() if row["submitted_at"] else None; row["has_attachment"]=bool(row.pop("attachment"))
    return {"records":rows,"page":page,"page_size":page_size,"total":total,"pages":max(1,(total+page_size-1)//page_size)}


def remove_draft(draft_id,removed_by,reason="",connection=None,commit=True):
    return draft_management.remove_draft(DRAFT_TABLE,draft_id,removed_by,reason,connection=connection,commit=commit)


def delete_submitted_transaction(draft_id, confirmation, reason, deleted_by, connection=None, commit=True):
    confirmation=_text(confirmation); reason=_text(reason)
    if not confirmation: raise ValueError("Type the transaction ID to confirm deletion")
    if not reason: raise ValueError("Deletion reason is required")
    owns=connection is None; connection=connection or _connect()
    if owns: connection.set_session(isolation_level="SERIALIZABLE",autocommit=False)
    try:
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(sql.SQL("SELECT * FROM {}.{} WHERE id=%s FOR UPDATE").format(sql.Identifier(_schema()),sql.Identifier(DRAFT_TABLE)),(int(draft_id),)); draft=cursor.fetchone()
            if not draft: raise LookupError("Submitted General Transaction not found")
            if draft.get("status")!="submitted" or draft.get("is_deleted"): raise ValueError("Only active submitted transactions can be deleted here")
            transaction_id=int(draft.get("submitted_transaction_id") or 0)
            if confirmation!=str(transaction_id): raise ValueError("Transaction ID confirmation does not match")
            cursor.execute(sql.SQL('DELETE FROM {}."_nc_m2m_Transection_category_master" WHERE "Transection_id"=%s').format(sql.Identifier(_schema())),(transaction_id,))
            cursor.execute(sql.SQL('DELETE FROM {}."Transection" WHERE id=%s').format(sql.Identifier(_schema())),(transaction_id,))
            cursor.execute(sql.SQL("DELETE FROM {}.{} WHERE id=%s AND status='submitted' RETURNING id").format(sql.Identifier(_schema()),sql.Identifier(DRAFT_TABLE)),(int(draft_id),))
            if not cursor.fetchone(): raise RuntimeError("Transaction changed concurrently; refresh and retry")
        if commit: connection.commit()
        return {"deleted":True,"draft_id":int(draft_id),"transaction_id":transaction_id,"confirmation":str(transaction_id),"attachment_path":draft.get("attachment_path"),"reason":reason,"deleted_by":deleted_by}
    except Exception: connection.rollback(); raise
    finally:
        if owns: connection.close()


def submission_details(draft_id):
    with _connect() as connection,connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute(sql.SQL("SELECT * FROM {}.{} WHERE id=%s AND status='submitted' AND is_deleted=false").format(sql.Identifier(_schema()),sql.Identifier(DRAFT_TABLE)),(int(draft_id),)); row=cursor.fetchone()
    if not row: raise LookupError("Submitted General Transaction not found")
    value = _payload(row)
    value["has_attachment"] = bool(value.pop("attachment_path", None))
    return value


def operational_summary():
    with _connect() as connection,connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute(sql.SQL('SELECT COUNT(*) FILTER (WHERE status<>\'submitted\' AND is_deleted=false) open_drafts,'
            'COUNT(*) FILTER (WHERE status=\'submitted\' AND submitted_at::date=CURRENT_DATE) transactions_today,'
            'COALESCE(SUM(amount) FILTER (WHERE status=\'submitted\' AND submitted_at::date=CURRENT_DATE AND transaction_type=\'Income\'),0) income_today,'
            'COALESCE(SUM(amount) FILTER (WHERE status=\'submitted\' AND submitted_at::date=CURRENT_DATE AND transaction_type=\'Expense\'),0) expense_today FROM {}.{}').format(sql.Identifier(_schema()),sql.Identifier(DRAFT_TABLE)))
        return dict(cursor.fetchone())
