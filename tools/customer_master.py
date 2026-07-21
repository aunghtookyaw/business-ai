"""Safe operational maintenance for the existing NocoDB Customer Master."""

from __future__ import annotations

import hashlib
import json
from difflib import SequenceMatcher
from uuid import UUID, uuid4

import psycopg2
import psycopg2.extras
from psycopg2 import sql

import config
from tools import formula_engine

GROUPS = {"Farm", "SotePhwar", "Both"}
PAGE_SIZES = {20, 50, 100}
FIELDS = ("customer_name", "phone_number", "town", "customer_group", "payment_terms_days", "contact_address", "notes")


class CustomerError(Exception):
    status_code = 400
    code = "invalid_customer"


class CustomerNotFound(CustomerError):
    status_code = 404
    code = "customer_not_found"


class DuplicateWarning(CustomerError):
    status_code = 409
    code = "possible_duplicate"

    def __init__(self, matches):
        super().__init__("Possible duplicate customer found")
        self.matches = matches


class ConcurrentEdit(CustomerError):
    status_code = 409
    code = "concurrent_modification"


def _schema():
    return config.TRANSACTION_SCHEMA


def _connect():
    return formula_engine._connect()


def _clean(value):
    return str(value or "").strip()


def _normalize(value):
    return " ".join(_clean(value).casefold().split())


def _validate(values):
    result = {field: _clean(values.get(field)) for field in FIELDS}
    result["customer_name"] = _clean(values.get("customer_name"))
    result["customer_group"] = _clean(values.get("customer_group"))
    if not result["customer_name"]:
        raise CustomerError("Customer name is required")
    if result["customer_group"] not in GROUPS:
        raise CustomerError("Customer group must be Farm, SotePhwar or Both")
    raw_terms = values.get("payment_terms_days")
    if raw_terms in (None, ""):
        result["payment_terms_days"] = 0
    else:
        try:
            result["payment_terms_days"] = int(raw_terms)
        except (TypeError, ValueError):
            raise CustomerError("Payment terms days must be a whole number")
        if not 0 <= result["payment_terms_days"] <= 3650:
            raise CustomerError("Payment terms days must be between 0 and 3650")
    return result


def _payload(row):
    value = dict(row)
    for key in ("created_at", "updated_at", "business_os_modified_at"):
        if value.get(key):
            value[key] = value[key].isoformat()
    value["active"] = bool(value.get("active"))
    value["business_os_version"] = int(value.get("business_os_version") or 1)
    return value


def new_submission_key():
    return str(uuid4())


def _submission_key(value):
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError, AttributeError):
        raise CustomerError("A valid server-generated submission key is required")


def summary():
    with _connect() as connection, connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute(sql.SQL("""
            SELECT COUNT(*) FILTER (WHERE active IS TRUE) active_customers,
                   COUNT(*) FILTER (WHERE active IS FALSE) inactive_customers,
                   COUNT(*) FILTER (WHERE active IS TRUE AND customer_group='Farm') farm_customers,
                   COUNT(*) FILTER (WHERE active IS TRUE AND customer_group='SotePhwar') sotephwar_customers,
                   COUNT(*) FILTER (WHERE active IS TRUE AND customer_group='Both') both_customers
            FROM {}.customer_master WHERE COALESCE(__nc_deleted,false)=false
        """).format(sql.Identifier(_schema())))
        return dict(cursor.fetchone())


def list_customers(filters=None, page=1, page_size=20):
    filters = filters or {}
    page = max(1, int(page or 1)); page_size = int(page_size or 20)
    if page_size not in PAGE_SIZES: page_size = 20
    params = {"limit": page_size, "offset": (page - 1) * page_size}
    clauses = ["COALESCE(__nc_deleted,false)=false", "NULLIF(btrim(customer_name),'') IS NOT NULL"]
    search = _clean(filters.get("q"))
    if search:
        params["search"] = f"%{search}%"
        clauses.append("(customer_name ILIKE %(search)s OR phone_number ILIKE %(search)s OR town ILIKE %(search)s OR contact_address ILIKE %(search)s)")
    for key in ("customer_name", "phone_number", "town"):
        value = _clean(filters.get(key))
        if value:
            params[key] = f"%{value}%"; clauses.append(f"{key} ILIKE %({key})s")
    if filters.get("customer_group") in GROUPS:
        params["customer_group"] = filters["customer_group"]; clauses.append("customer_group=%(customer_group)s")
    if filters.get("active") in ("true", "false"):
        params["active"] = filters["active"] == "true"; clauses.append("active=%(active)s")
    if filters.get("recent") == "true":
        clauses.append("(created_at >= now() - interval '30 days' OR EXISTS (SELECT 1 FROM "
                       + _schema() + ".business_os_customer_submission cs WHERE cs.customer_id=customer_master.id "
                       "AND cs.action='create' AND cs.completed_at >= now() - interval '30 days'))")
    where = " AND ".join(clauses)
    query = sql.SQL("""SELECT id,customer_name,phone_number,town,customer_group,payment_terms_days,
        contact_address,notes,active,created_at,updated_at,business_os_modified_at,business_os_version,
        COUNT(*) OVER() total_count FROM {}.customer_master WHERE """ + where +
        " ORDER BY COALESCE(business_os_modified_at,updated_at,created_at) DESC NULLS LAST,customer_name,id LIMIT %(limit)s OFFSET %(offset)s").format(sql.Identifier(_schema()))
    with _connect() as connection, connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute(query, params); rows = [dict(row) for row in cursor.fetchall()]
    total = int(rows[0].pop("total_count")) if rows else 0
    return {"customers": [_payload(row) for row in rows], "page": page, "page_size": page_size,
            "total": total, "pages": max(1, (total + page_size - 1) // page_size)}


def get_customer(customer_id, connection=None, lock=False):
    owns = connection is None; connection = connection or _connect()
    try:
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(sql.SQL("SELECT id,customer_name,phone_number,town,customer_group,payment_terms_days,contact_address,notes,active,created_at,updated_at,business_os_modified_at,business_os_version FROM {}.customer_master WHERE id=%s AND COALESCE(__nc_deleted,false)=false" + (" FOR UPDATE" if lock else "")).format(sql.Identifier(_schema())), (int(customer_id),))
            row = cursor.fetchone()
        if not row: raise CustomerNotFound("Customer not found")
        return _payload(row)
    finally:
        if owns: connection.close()


def duplicate_matches(values, exclude_id=None, connection=None):
    name, phone, town = _normalize(values.get("customer_name")), _clean(values.get("phone_number")), _normalize(values.get("town"))
    params = {"name": name, "phone": phone, "town": town, "exclude": int(exclude_id or 0)}
    owns = connection is None
    connection = connection or _connect()
    try:
      with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute(sql.SQL("""SELECT id,customer_name,phone_number,town,customer_group,active
          FROM {}.customer_master WHERE COALESCE(__nc_deleted,false)=false AND id<>%(exclude)s AND (
          lower(regexp_replace(btrim(customer_name),'\\s+',' ','g'))=%(name)s OR
          (%(phone)s<>'' AND btrim(phone_number)=%(phone)s) OR
          (%(town)s<>'' AND lower(regexp_replace(btrim(town),'\\s+',' ','g'))=%(town)s))
          ORDER BY id LIMIT 30""").format(sql.Identifier(_schema())), params)
        candidates = [dict(row) for row in cursor.fetchall()]
    finally:
        if owns: connection.close()
    matches = []
    for row in candidates:
        row_name, row_phone, row_town = _normalize(row["customer_name"]), _clean(row["phone_number"]), _normalize(row["town"])
        reasons = []
        if name and row_name == name: reasons.append("same normalized name")
        if phone and row_phone == phone: reasons.append("same phone number")
        if name and town and row_name == name and row_town == town: reasons.append("same name and town")
        if name and town and row_town == town and SequenceMatcher(None, name, row_name).ratio() >= .84: reasons.append("similar name and same town")
        if reasons: matches.append({**row, "reasons": reasons})
    return matches


def _request_hash(action, values):
    return hashlib.sha256(json.dumps({"action": action, "values": values}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _begin_submission(cursor, key, action, request_hash):
    cursor.execute(sql.SQL("SELECT action,request_hash,response_json FROM {}.business_os_customer_submission WHERE submission_key=%s FOR UPDATE").format(sql.Identifier(_schema())), (key,))
    existing = cursor.fetchone()
    if existing:
        if existing[0] != action or existing[1] != request_hash: raise CustomerError("Submission key was already used for a different request")
        if existing[2] is not None: return existing[2]
        raise ConcurrentEdit("Submission is already in progress")
    cursor.execute(sql.SQL("INSERT INTO {}.business_os_customer_submission(submission_key,action,request_hash) VALUES (%s,%s,%s)").format(sql.Identifier(_schema())), (key, action, request_hash))


def create_customer(values, submission_key, operator="data-entry", allow_duplicate=False):
    clean = _validate(values); submission_key = _submission_key(submission_key); request_hash = _request_hash("create", clean)
    with _connect() as connection:
        connection.set_session(isolation_level="SERIALIZABLE")
        with connection.cursor() as cursor:
            replay = _begin_submission(cursor, submission_key, "create", request_hash)
            if replay is not None: return replay
            matches = duplicate_matches(clean, connection=connection)
            if matches and not allow_duplicate: raise DuplicateWarning(matches)
            cursor.execute(sql.SQL("""INSERT INTO {}.customer_master
              (customer_name,phone_number,town,customer_group,payment_terms_days,contact_address,notes,active,business_os_modified_at,business_os_modified_by)
              VALUES (%s,%s,%s,%s,%s,%s,%s,true,now(),%s) RETURNING id""").format(sql.Identifier(_schema())),
              tuple(clean[field] for field in FIELDS) + (operator,))
            customer_id = cursor.fetchone()[0]; result = get_customer(customer_id, connection)
            cursor.execute(sql.SQL("UPDATE {}.business_os_customer_submission SET customer_id=%s,response_json=%s::jsonb,completed_at=now() WHERE submission_key=%s").format(sql.Identifier(_schema())), (customer_id, json.dumps(result), submission_key))
        connection.commit(); return result


def update_customer(customer_id, values, expected_version, submission_key, operator="data-entry"):
    clean = _validate(values); submission_key = _submission_key(submission_key)
    try: expected_version = int(expected_version)
    except (TypeError, ValueError): raise CustomerError("Customer version is required")
    request = {**clean, "customer_id": int(customer_id), "expected_version": expected_version}; request_hash = _request_hash("update", request)
    with _connect() as connection:
        connection.set_session(isolation_level="SERIALIZABLE")
        with connection.cursor() as cursor:
            replay = _begin_submission(cursor, submission_key, "update", request_hash)
            if replay is not None: return replay
            current = get_customer(customer_id, connection, lock=True)
            if current["business_os_version"] != int(expected_version): raise ConcurrentEdit("Customer was changed by another user; reload before saving")
            matches = duplicate_matches(clean, exclude_id=customer_id, connection=connection)
            if matches: raise DuplicateWarning(matches)
            cursor.execute(sql.SQL("""UPDATE {}.customer_master SET customer_name=%s,phone_number=%s,town=%s,customer_group=%s,
              payment_terms_days=%s,contact_address=%s,notes=%s,business_os_version=business_os_version+1,
              business_os_modified_at=now(),business_os_modified_by=%s WHERE id=%s RETURNING id""").format(sql.Identifier(_schema())),
              tuple(clean[field] for field in FIELDS) + (operator, int(customer_id)))
            result = get_customer(customer_id, connection)
            cursor.execute(sql.SQL("UPDATE {}.business_os_customer_submission SET customer_id=%s,response_json=%s::jsonb,completed_at=now() WHERE submission_key=%s").format(sql.Identifier(_schema())), (customer_id, json.dumps(result), submission_key))
        connection.commit(); return result


def set_active(customer_id, active, expected_version, submission_key, operator):
    submission_key = _submission_key(submission_key)
    if not isinstance(active, bool): raise CustomerError("Active status must be true or false")
    try: expected_version = int(expected_version)
    except (TypeError, ValueError): raise CustomerError("Customer version is required")
    request = {"customer_id": int(customer_id), "active": bool(active), "expected_version": expected_version}; request_hash = _request_hash("status", request)
    with _connect() as connection:
        connection.set_session(isolation_level="SERIALIZABLE")
        with connection.cursor() as cursor:
            replay = _begin_submission(cursor, submission_key, "status", request_hash)
            if replay is not None: return replay
            current = get_customer(customer_id, connection, lock=True)
            if current["business_os_version"] != int(expected_version): raise ConcurrentEdit("Customer was changed by another user; reload before saving")
            cursor.execute(sql.SQL("UPDATE {}.customer_master SET active=%s,business_os_version=business_os_version+1,business_os_modified_at=now(),business_os_modified_by=%s WHERE id=%s").format(sql.Identifier(_schema())), (bool(active), operator, int(customer_id)))
            result = get_customer(customer_id, connection)
            cursor.execute(sql.SQL("UPDATE {}.business_os_customer_submission SET customer_id=%s,response_json=%s::jsonb,completed_at=now() WHERE submission_key=%s").format(sql.Identifier(_schema())), (customer_id, json.dumps(result), submission_key))
        connection.commit(); return result


def customer_detail(customer_id):
    customer = get_customer(customer_id)
    schema = sql.Identifier(_schema())
    with _connect() as connection, connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute(sql.SQL('SELECT f.id,f."Invoice_Number" AS reference,f."Date" AS activity_date,f."Total_Amount" AS amount,f."Payment_Status" AS payment_status FROM {}.farm_transection f JOIN {}."_nc_m2m_farm_transectio_customer_master" l ON l."farm_transection_id"=f.id WHERE l.customer_master_id=%s AND COALESCE(f.__nc_deleted,false)=false ORDER BY f."Date" DESC NULLS LAST,f.id DESC LIMIT 10').format(schema, schema), (int(customer_id),)); farm = [dict(row) for row in cursor.fetchall()]
        cursor.execute(sql.SQL('SELECT s.id,s."Invoice_Number" AS reference,s."Invoice_Date" AS activity_date,s."Item" AS item,s."Total_Amount" AS amount,s."Payment_Status" AS payment_status FROM {}."Sotephwar_Transection" s JOIN {}."_nc_m2m_Sotephwar_Trans_customer_master" l ON l."Sotephwar_Transection_id"=s.id WHERE l.customer_master_id=%s AND COALESCE(s.__nc_deleted,false)=false ORDER BY s."Invoice_Date" DESC NULLS LAST,s.id DESC LIMIT 10').format(schema, schema), (int(customer_id),)); sote = [dict(row) for row in cursor.fetchall()]
    for rows in (farm, sote):
        for row in rows:
            if row.get("activity_date"): row["activity_date"] = row["activity_date"].isoformat()
            row["amount"] = int(row.get("amount") or 0)
    return {"customer": customer, "recent_farm_vouchers": farm, "recent_sotephwar_vouchers": sote,
            "activity_note": "Payments are omitted because the current payment table has no authoritative Customer Master relationship."}
