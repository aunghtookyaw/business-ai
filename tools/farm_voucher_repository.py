"""PostgreSQL persistence and atomic submit adapter for Farm Voucher."""
import hashlib
import json
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import tempfile

import psycopg2.extras
from psycopg2 import sql

import config
from tools.formula_engine import _connect
from tools import voucher_engine
from tools import draft_management
from tools.farm_voucher_pdf import write_farm_voucher_pdf


DRAFT_TABLE = "business_os_voucher_draft"
ROOT = Path(__file__).resolve().parents[1]
SUBMITTED_PDF_DIR = ROOT / "output" / "pdf" / "submitted"
CUSTOMER_FIELDS = (
    "id", "customer_name", "phone_number", "town", "contact_address",
    "payment_terms_days", "customer_group", "active",
)


def _schema():
    return config.TRANSACTION_SCHEMA


def _json_value(value):
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"Unsupported JSON value: {type(value).__name__}")


def _payload(row):
    if not row:
        return None
    value = dict(row)
    value["lines"] = value.get("lines") or []
    value["delivery_sections"] = value.get("delivery_sections") or voucher_engine._section_source(value)
    value["customer_snapshot"] = value.get("customer_snapshot") or {}
    value["submitted_voucher"] = value.get("submitted_voucher") or {}
    metadata = value.get("voucher_metadata") or {}
    value.update({
        "discount_amount": str(metadata.get("discount_amount") or 0),
        "cashback_amount": str(metadata.get("cashback_amount") or 0),
        "adjustment_reason": str(metadata.get("adjustment_reason") or ""),
    })
    try:
        gross = sum((Decimal(str(item.get("quantity") or 0)) * Decimal(str(item.get("unit_price") or 0))
                     for section in value["delivery_sections"] for item in (section.get("items") or [])), Decimal("0"))
        value["gross_amount"] = str(gross)
        value["net_amount"] = str(gross - Decimal(value["discount_amount"]) - Decimal(value["cashback_amount"]))
    except Exception:
        value["gross_amount"] = str(value.get("total_amount") or 0)
        value["net_amount"] = str(value.get("total_amount") or 0)
    for key in ("amount_received", "total_amount"):
        value[key] = str(value.get(key) or 0)
    for key in ("voucher_date", "created_at", "updated_at", "submitted_at"):
        if value.get(key):
            value[key] = value[key].isoformat()
    return value


def list_drafts(limit=50):
    with _connect() as connection, connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute(
            sql.SQL("SELECT * FROM {}.{} WHERE sector = 'farm' AND status<>'submitted' AND is_deleted=false ORDER BY updated_at DESC LIMIT %s").format(
                sql.Identifier(_schema()), sql.Identifier(DRAFT_TABLE)
            ),
            (max(1, min(int(limit), 100)),),
        )
        return [_payload(row) for row in cursor.fetchall()]


def list_customers():
    with _connect() as connection, connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute(
            sql.SQL(
                'SELECT id, customer_name, "Customer_Code" AS customer_code, "Region" AS region, '
                'phone_number, town, contact_address, payment_terms_days, customer_group, active '
                'FROM {}.customer_master WHERE COALESCE(__nc_deleted,false)=false '
                "AND NULLIF(TRIM(customer_name),'') IS NOT NULL "
                "AND customer_group IN ('Farm','Both') AND active IS TRUE ORDER BY customer_name,id"
            ).format(sql.Identifier(_schema()))
        )
        return [dict(row) for row in cursor.fetchall() if _customer_is_eligible(row)]


def _customer_is_eligible(row):
    return bool(
        row and row.get("active") is True
        and row.get("customer_group") in {"Farm", "Both"}
        and str(row.get("customer_name") or "").strip()
    )


def _snapshot_from_customer(row):
    if not row:
        return None
    snapshot = {key: row.get(key) for key in CUSTOMER_FIELDS}
    snapshot["id"] = int(snapshot["id"])
    snapshot["customer_name"] = str(snapshot.get("customer_name") or "").strip()
    snapshot["phone_number"] = str(snapshot.get("phone_number") or "").strip()
    snapshot["town"] = str(snapshot.get("town") or "").strip()
    snapshot["contact_address"] = str(snapshot.get("contact_address") or "").strip()
    if snapshot.get("payment_terms_days") is not None:
        snapshot["payment_terms_days"] = int(snapshot["payment_terms_days"])
    snapshot["active"] = bool(snapshot.get("active"))
    return snapshot


def _load_customer_snapshot(customer_id, connection):
    if customer_id in (None, ""):
        return {}
    with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute(
            sql.SQL(
                'SELECT id,customer_name,phone_number,town,contact_address,payment_terms_days,customer_group,active '
                'FROM {}.customer_master WHERE id=%s AND COALESCE(__nc_deleted,false)=false '
                "AND customer_group IN ('Farm','Both') AND active IS TRUE"
            ).format(sql.Identifier(_schema())),
            (int(customer_id),),
        )
        snapshot = _snapshot_from_customer(cursor.fetchone())
    if not snapshot:
        raise voucher_engine.VoucherValidationError(["active Farm/Both Customer Master record not found"])
    return snapshot


def _draft_customer_snapshot(values, current, connection):
    customer_id = (values or {}).get("customer_id")
    if customer_id in (None, ""):
        return {}
    existing = (current or {}).get("customer_snapshot") or {}
    if existing and int((current or {}).get("customer_id") or 0) == int(customer_id):
        return existing
    return _load_customer_snapshot(customer_id, connection)


def list_crops():
    with _connect() as connection, connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute(
            '''SELECT id, crop_code, crop_name, default_unit, category, display_order
               FROM public.veggies_crop_master
               WHERE active = TRUE
               ORDER BY display_order NULLS LAST, crop_name, id'''
        )
        return [dict(row) for row in cursor.fetchall()]


def _storage_sections(draft):
    sections = deepcopy(voucher_engine._section_source(draft))
    legacy_lines = []
    for section in sections:
        delivery_date = section.get("delivery_date")
        for item in section.get("items") or []:
            crop_id = item.get("crop_id")
            description = item.get("crop_name") if crop_id else item.get("custom_description")
            legacy_lines.append({**item, "description": description or "", "delivery_date": delivery_date})
    return sections, legacy_lines


def _hydrate_crop_names(draft, connection=None):
    value = deepcopy(draft)
    sections = voucher_engine._section_source(value)
    crop_ids = sorted({int(item["crop_id"]) for section in sections for item in (section.get("items") or []) if item.get("crop_id") not in (None, "")})
    if crop_ids:
        owns = connection is None
        connection = connection or _connect()
        try:
            with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
                cursor.execute(
                    '''SELECT id, crop_name, default_unit FROM public.veggies_crop_master
                       WHERE id = ANY(%s) AND active = TRUE''',
                    (crop_ids,),
                )
                crops = {int(row["id"]): dict(row) for row in cursor.fetchall()}
        finally:
            if owns:
                connection.close()
        missing = [crop_id for crop_id in crop_ids if crop_id not in crops]
        if missing:
            raise voucher_engine.VoucherValidationError([f"active Crop Master record not found: {crop_id}" for crop_id in missing])
        for section in sections:
            for item in section.get("items") or []:
                if item.get("crop_id") not in (None, ""):
                    crop = crops[int(item["crop_id"])]
                    item["crop_id"] = int(item["crop_id"])
                    item["crop_name"] = crop["crop_name"]
    value["delivery_sections"] = sections
    return value


def get_draft(draft_id, connection=None, for_update=False):
    owns = connection is None
    connection = connection or _connect()
    try:
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(
                sql.SQL("SELECT * FROM {}.{} WHERE id = %s AND sector = 'farm' AND is_deleted=false{}").format(
                    sql.Identifier(_schema()), sql.Identifier(DRAFT_TABLE),
                    sql.SQL(" FOR UPDATE" if for_update else ""),
                ),
                (int(draft_id),),
            )
            return _payload(cursor.fetchone())
    finally:
        if owns:
            connection.close()


def create_draft(values, created_by):
    draft = voucher_engine.new_draft("farm")
    draft.update(values or {})
    draft["sector"] = "farm"
    sections, lines = _storage_sections(draft)
    with _connect() as connection, connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        snapshot = _draft_customer_snapshot(draft, None, connection)
        draft["customer_name"] = snapshot.get("customer_name", "")
        cursor.execute(
            sql.SQL(
                "INSERT INTO {}.{} (sector,status,voucher_number,voucher_date,customer_id,customer_name,"
                "customer_snapshot,payment_method,note,amount_received,lines,delivery_sections,voucher_metadata,total_amount,created_by) "
                "VALUES ('farm','draft',%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,0,%s) RETURNING *"
            ).format(sql.Identifier(_schema()), sql.Identifier(DRAFT_TABLE)),
            (str(draft.get("voucher_number") or ""), draft.get("voucher_date"), draft.get("customer_id"),
             str(draft.get("customer_name") or ""), json.dumps(snapshot), str(draft.get("payment_method") or ""),
             str(draft.get("note") or ""), draft.get("amount_received") or 0,
             json.dumps(lines, default=_json_value), json.dumps(sections, default=_json_value),
             json.dumps({"discount_amount": draft.get("discount_amount", 0), "cashback_amount": draft.get("cashback_amount", 0), "adjustment_reason": draft.get("adjustment_reason", "")}), created_by),
        )
        row = cursor.fetchone()
        connection.commit()
        return _payload(row)


def update_draft(draft_id, values, expected_version):
    current = get_draft(draft_id)
    if not current:
        raise LookupError("Farm voucher draft not found")
    if current["status"] == "submitted":
        raise ValueError("Submitted vouchers cannot be edited")
    merged = {**current, **(values or {}), "sector": "farm", "status": "draft"}
    with _connect() as connection, connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        snapshot = _draft_customer_snapshot(merged, current, connection)
        merged["customer_name"] = snapshot.get("customer_name", "")
        sections, lines = _storage_sections(merged)
        cursor.execute(
            sql.SQL(
                "UPDATE {}.{} SET status='draft',voucher_number=%s,voucher_date=%s,customer_id=%s,"
                "customer_name=%s,customer_snapshot=%s::jsonb,payment_method=%s,note=%s,amount_received=%s,lines=%s::jsonb,delivery_sections=%s::jsonb,voucher_metadata=%s::jsonb,total_amount=0,"
                "version=version+1,updated_at=now() WHERE id=%s AND sector='farm' AND version=%s RETURNING *"
            ).format(sql.Identifier(_schema()), sql.Identifier(DRAFT_TABLE)),
            (str(merged.get("voucher_number") or ""), merged.get("voucher_date"), merged.get("customer_id"),
             str(merged.get("customer_name") or ""), json.dumps(snapshot), str(merged.get("payment_method") or ""),
             str(merged.get("note") or ""), merged.get("amount_received") or 0,
             json.dumps(lines, default=_json_value), json.dumps(sections, default=_json_value),
             json.dumps({"discount_amount": merged.get("discount_amount", 0), "cashback_amount": merged.get("cashback_amount", 0), "adjustment_reason": merged.get("adjustment_reason", "")}), int(draft_id), int(expected_version)),
        )
        row = cursor.fetchone()
        if not row:
            raise RuntimeError("Draft changed in another session; refresh and retry")
        connection.commit()
        return _payload(row)


def set_workflow_state(draft_id, state):
    draft = get_draft(draft_id)
    if not draft:
        raise LookupError("Farm voucher draft not found")
    hydrated = _hydrate_crop_names(draft)
    normalized = voucher_engine.preview(hydrated) if state == "previewed" else voucher_engine.validate(hydrated)
    sections, lines = _storage_sections(normalized)
    with _connect() as connection, connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute(
            sql.SQL("UPDATE {}.{} SET status=%s,total_amount=%s,amount_received=%s,lines=%s::jsonb,delivery_sections=%s::jsonb,voucher_metadata=%s::jsonb,updated_at=now(),version=version+1 WHERE id=%s AND status<>'submitted' RETURNING *").format(
                sql.Identifier(_schema()), sql.Identifier(DRAFT_TABLE)
            ),
            (state, normalized.get("total_amount", 0), normalized.get("amount_received", draft.get("amount_received", 0)),
             json.dumps(lines, default=_json_value), json.dumps(sections, default=_json_value),
             json.dumps({"discount_amount": normalized["discount_amount"], "cashback_amount": normalized["cashback_amount"], "adjustment_reason": normalized["adjustment_reason"]}, default=_json_value), int(draft_id)),
        )
        row = cursor.fetchone()
        if not row:
            raise ValueError("Submitted vouchers cannot change workflow state")
        connection.commit()
    return {"draft": _payload(row), "voucher": normalized}


def _prepare_final_pdf(draft_id, voucher, pdf_directory=None):
    """Write and checksum the final PDF before any accounting row is inserted."""
    directory = Path(pdf_directory or SUBMITTED_PDF_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    number = "".join(character for character in str(voucher["voucher_number"]) if character.isalnum() or character in "-_")
    final_path = directory / f"Farm_Voucher_{number}_draft_{int(draft_id)}.pdf"
    handle = tempfile.NamedTemporaryFile(dir=directory, prefix=".farm-voucher-", suffix=".pdf", delete=False)
    temporary_path = Path(handle.name)
    handle.close()
    try:
        write_farm_voucher_pdf(voucher, temporary_path)
        if not temporary_path.exists() or temporary_path.stat().st_size == 0:
            raise RuntimeError("Final Farm Voucher PDF generation produced an empty file")
        checksum = hashlib.sha256(temporary_path.read_bytes()).hexdigest()
        temporary_path.replace(final_path)
        return final_path.resolve(), checksum
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def submitted_pdf_path(draft):
    """Return a checksum-verified immutable submitted PDF path."""
    path_value = str((draft or {}).get("submitted_pdf_path") or "").strip()
    checksum = str((draft or {}).get("submitted_pdf_checksum") or "").strip()
    if not path_value or not checksum:
        raise RuntimeError("Submitted voucher PDF metadata is unavailable")
    path = Path(path_value)
    if not path.is_file():
        raise RuntimeError("Submitted voucher PDF file is unavailable")
    if hashlib.sha256(path.read_bytes()).hexdigest() != checksum:
        raise RuntimeError("Submitted voucher PDF checksum verification failed")
    return path


def submit(draft_id, submitted_by, connection=None, commit=True, pdf_directory=None):
    """Atomically insert the Farm transaction, link its customer, and close the draft."""
    owns_connection = connection is None
    connection = connection or _connect()
    if owns_connection:
        connection.set_session(isolation_level="SERIALIZABLE", autocommit=False)
    prepared_pdf = None
    try:
        draft = get_draft(draft_id, connection=connection, for_update=True)
        if not draft:
            raise LookupError("Farm voucher draft not found")
        if draft["status"] == "submitted":
            return {
                "draft": draft, "transaction_id": draft["submitted_transaction_id"], "idempotent": True,
                "pdf_path": draft.get("submitted_pdf_path"), "pdf_checksum": draft.get("submitted_pdf_checksum"),
            }
        if draft["status"] not in {"validated", "previewed"}:
            raise voucher_engine.VoucherValidationError(["voucher must be successfully validated before submit"])
        draft = _hydrate_crop_names(draft, connection=connection)
        voucher = voucher_engine.preview(draft)
        row = voucher_engine.farm_transaction_rows(voucher)[0]
        if not draft.get("customer_id"):
            raise voucher_engine.VoucherValidationError(["customer_id is required for submit"])
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (
                f'Farm|{row["Invoice_Number"]}|{row["Date"]}|{row["Customer"]}',
            ))
            cursor.execute(
                sql.SQL(
                    'SELECT id FROM {}.farm_transection WHERE COALESCE(__nc_deleted,false)=false '
                    'AND "Invoice_Number"=%s AND "Date"=%s AND COALESCE("Customer",\'\')=%s LIMIT 1'
                ).format(sql.Identifier(_schema())),
                (int(row["Invoice_Number"]), row["Date"], row["Customer"]),
            )
            if cursor.fetchone():
                raise ValueError("A Farm voucher with this number, date, and customer already exists")
            cursor.execute(
                sql.SQL(
                    'SELECT id FROM {}.customer_master WHERE id=%s AND COALESCE(__nc_deleted,false)=false FOR SHARE'
                ).format(sql.Identifier(_schema())),
                (int(draft["customer_id"]),),
            )
            customer = cursor.fetchone()
            if not customer:
                raise ValueError("Selected Customer Master no longer exists")
            prepared_pdf = _prepare_final_pdf(draft_id, voucher, pdf_directory)
            cursor.execute(
                sql.SQL(
                    'INSERT INTO {}.farm_transection ("Date","Customer","Invoice_Number","Total_Amount",'
                    '"Total_Received","Outstanding_Balance","Payment_Status") '
                    'VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id'
                ).format(sql.Identifier(_schema())),
                (row["Date"], row["Customer"], int(row["Invoice_Number"]), row["Total_Amount"],
                 row["Total_Received"], row["Outstanding_Balance"], row["Payment_Status"]),
            )
            transaction_id = cursor.fetchone()["id"]
            cursor.execute(
                sql.SQL(
                    'INSERT INTO {}."_nc_m2m_farm_transectio_customer_master" '
                    '(customer_master_id,farm_transection_id) VALUES (%s,%s)'
                ).format(sql.Identifier(_schema())),
                (int(draft["customer_id"]), transaction_id),
            )
            submitted_voucher = deepcopy(voucher)
            submitted_voucher.update({
                "status": "submitted", "submitted_transaction_id": transaction_id,
                "submitted_by": submitted_by,
            })
            cursor.execute(
                sql.SQL(
                    "UPDATE {}.{} SET status='submitted',total_amount=%s,submitted_transaction_id=%s,"
                    "submitted_voucher=%s::jsonb,submitted_pdf_path=%s,submitted_pdf_checksum=%s,"
                    "submitted_at=now(),updated_at=now(),version=version+1 WHERE id=%s RETURNING *"
                ).format(sql.Identifier(_schema()), sql.Identifier(DRAFT_TABLE)),
                (row["Total_Amount"], transaction_id, json.dumps(submitted_voucher, default=_json_value),
                 str(prepared_pdf[0]), prepared_pdf[1], int(draft_id)),
            )
            saved = _payload(cursor.fetchone())
        if commit:
            connection.commit()
        return {
            "draft": saved, "transaction_id": transaction_id, "idempotent": False,
            "submitted_by": submitted_by, "pdf_path": str(prepared_pdf[0]), "pdf_checksum": prepared_pdf[1],
        }
    except Exception:
        connection.rollback()
        if prepared_pdf:
            Path(prepared_pdf[0]).unlink(missing_ok=True)
        raise
    finally:
        if owns_connection:
            connection.close()


def remove_draft(draft_id, removed_by, reason="", connection=None, commit=True):
    return draft_management.remove_draft(DRAFT_TABLE, draft_id, removed_by, reason, "farm", connection, commit)


def delete_submitted_voucher(draft_id, voucher_number, reason, deleted_by, connection=None, commit=True):
    confirmed=str(voucher_number or "").strip(); reason=str(reason or "").strip()
    if not confirmed: raise ValueError("Type the voucher number to confirm deletion")
    if not reason: raise ValueError("Deletion reason is required")
    owns=connection is None; connection=connection or _connect()
    if owns: connection.set_session(isolation_level="SERIALIZABLE",autocommit=False)
    try:
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(sql.SQL("SELECT * FROM {}.{} WHERE id=%s AND sector='farm' FOR UPDATE").format(sql.Identifier(_schema()),sql.Identifier(DRAFT_TABLE)),(int(draft_id),)); draft=cursor.fetchone()
            if not draft: raise LookupError("Submitted Farm voucher not found")
            if draft.get("status")!="submitted" or draft.get("is_deleted"): raise ValueError("Only active submitted vouchers can be deleted here")
            actual=str(draft.get("voucher_number") or "")
            if confirmed!=actual: raise ValueError("Voucher number confirmation does not match")
            cursor.execute(sql.SQL('SELECT COUNT(*) count FROM {}."Payment_Receive" WHERE "Sector"=\'Farm\' AND "Voucher_Number"=%s AND "Customer"=%s AND ("Invoice_Date"=%s OR "Invoice_Date" IS NULL)').format(sql.Identifier(_schema())),(actual,draft.get("customer_name") or "",draft.get("voucher_date")))
            if int(cursor.fetchone()["count"] or 0): raise ValueError("Voucher has payment history and cannot be deleted")
            transaction_id=draft.get("submitted_transaction_id")
            if transaction_id:
                cursor.execute(sql.SQL('DELETE FROM {}."_nc_m2m_farm_transectio_customer_master" WHERE farm_transection_id=%s').format(sql.Identifier(_schema())),(int(transaction_id),))
                cursor.execute(sql.SQL('DELETE FROM {}.farm_transection WHERE id=%s').format(sql.Identifier(_schema())),(int(transaction_id),))
            cursor.execute(sql.SQL("DELETE FROM {}.{} WHERE id=%s AND sector='farm' AND status='submitted' RETURNING id").format(sql.Identifier(_schema()),sql.Identifier(DRAFT_TABLE)),(int(draft_id),))
            if not cursor.fetchone(): raise RuntimeError("Voucher changed concurrently; refresh and retry")
        if commit: connection.commit()
        return {"deleted":True,"draft_id":int(draft_id),"voucher_number":actual,"customer_name":draft.get("customer_name") or "","transaction_ids":[int(transaction_id)] if transaction_id else [],"pdf_path":draft.get("submitted_pdf_path"),"reason":reason,"deleted_by":deleted_by}
    except Exception: connection.rollback(); raise
    finally:
        if owns: connection.close()


def recent_submissions(filters=None, page=1, page_size=20):
    filters = filters or {}; page, page_size, offset = draft_management.paging(page, page_size)
    clauses = ["d.sector='farm'", "d.status='submitted'", "d.is_deleted=false", "d.submitted_transaction_id IS NOT NULL"]
    params = {"limit": page_size, "offset": offset}
    for key, column in (("date_from", 'f."Date">='), ("date_to", 'f."Date"<='), ("customer", 'f."Customer" ILIKE'),
                        ("voucher_number", 'f."Invoice_Number"::text='), ("payment_status", 'f."Payment_Status"=')):
        value = filters.get(key)
        if value:
            params[key] = f"%{value}%" if key == "customer" else value
            clauses.append(f"{column}%({key})s")
    where = " AND ".join(clauses)
    with _connect() as connection, connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute(sql.SQL('SELECT d.id AS draft_id,d.voucher_number,d.voucher_date,d.customer_name,d.submitted_at,'
            'd.submitted_pdf_path,d.submitted_pdf_checksum,d.submitted_voucher,f.id AS record_id,f."Total_Amount" AS total_amount,'
            'f."Total_Received" AS total_received,f."Outstanding_Balance" AS outstanding_balance,'
            'f."Payment_Status" AS payment_status,COUNT(*) OVER() AS total_count FROM {}.{} d '
            'JOIN {}.farm_transection f ON f.id=d.submitted_transaction_id WHERE '+where+
            ' ORDER BY d.submitted_at DESC,d.id DESC LIMIT %(limit)s OFFSET %(offset)s').format(
                sql.Identifier(_schema()),sql.Identifier(DRAFT_TABLE),sql.Identifier(_schema())),params)
        rows=[dict(row) for row in cursor.fetchall()]
    total=int(rows[0].pop("total_count")) if rows else 0
    for row in rows:
        voucher = row.pop("submitted_voucher") or {}
        previous_total = voucher.get("total_amount", row.get("total_amount") or 0)
        row["gross_amount"] = str(voucher.get("gross_amount", previous_total) or 0)
        row["discount_amount"] = str(voucher.get("discount_amount", 0) or 0)
        row["cashback_amount"] = str(voucher.get("cashback_amount", 0) or 0)
        row["net_amount"] = str(voucher.get("net_amount", previous_total) or 0)
        row["voucher_date"]=row["voucher_date"].isoformat(); row["submitted_at"]=row["submitted_at"].isoformat() if row["submitted_at"] else None
        for key in ("total_amount","total_received","outstanding_balance"): row[key]=str(row.get(key) or 0)
        pdf_path = row.pop("submitted_pdf_path", None)
        pdf_checksum = row.pop("submitted_pdf_checksum", None)
        row["pdf_available"] = bool(pdf_path and pdf_checksum)
    return {"records":rows,"page":page,"page_size":page_size,"total":total,"pages":max(1,(total+page_size-1)//page_size)}


def submission_details(draft_id):
    with _connect() as connection, connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute(sql.SQL("SELECT * FROM {}.{} WHERE id=%s AND sector='farm' AND status='submitted' AND is_deleted=false").format(
            sql.Identifier(_schema()),sql.Identifier(DRAFT_TABLE)),(int(draft_id),))
        row=cursor.fetchone()
    if not row: raise LookupError("Submitted Farm voucher not found")
    value = _payload(row)
    pdf_path = value.pop("submitted_pdf_path", None)
    pdf_checksum = value.pop("submitted_pdf_checksum", None)
    value["pdf_available"] = bool(pdf_path and pdf_checksum)
    return value


def operational_summary():
    with _connect() as connection, connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute(sql.SQL('SELECT COUNT(*) FILTER (WHERE status<>\'submitted\' AND is_deleted=false) AS open_drafts,'
            'COUNT(*) FILTER (WHERE status=\'submitted\' AND submitted_at::date=CURRENT_DATE) AS submitted_today,'
            'COALESCE(SUM(total_amount) FILTER (WHERE status=\'submitted\' AND submitted_at::date=CURRENT_DATE),0) AS total_today,'
            'COALESCE(SUM((submitted_voucher->>\'outstanding_balance\')::numeric) FILTER (WHERE status=\'submitted\' AND submitted_at::date=CURRENT_DATE),0) AS outstanding_today '
            'FROM {}.{} WHERE sector=\'farm\'').format(sql.Identifier(_schema()),sql.Identifier(DRAFT_TABLE)))
        return dict(cursor.fetchone())
