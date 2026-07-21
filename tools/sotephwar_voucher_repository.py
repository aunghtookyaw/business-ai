"""PostgreSQL persistence and atomic submit adapter for SotePhwar Voucher."""
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
from tools.sotephwar_voucher_pdf import write_sotephwar_voucher_pdf


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
    value["customer_snapshot"] = value.get("customer_snapshot") or {}
    value["submitted_voucher"] = value.get("submitted_voucher") or {}
    value["submitted_transaction_ids"] = value.get("submitted_transaction_ids") or []
    metadata = value.get("voucher_metadata") or {}
    value.update({
        "discount_amount": str(metadata.get("discount_amount") or 0),
        "cashback_amount": str(metadata.get("cashback_amount") or 0),
        "adjustment_reason": str(metadata.get("adjustment_reason") or ""),
        "free_lines": metadata.get("free_lines") or [],
    })
    try:
        gross = sum((Decimal(str(line.get("quantity") or 0)) * Decimal(str(line.get("unit_price") or 0))
                     for line in value["lines"]), Decimal("0"))
        value["gross_amount"] = str(gross)
        value["net_amount"] = str(gross - Decimal(value["discount_amount"]) - Decimal(value["cashback_amount"]))
    except Exception:
        value["gross_amount"] = str(value.get("total_amount") or 0)
        value["net_amount"] = str(value.get("total_amount") or 0)
    for key in ("amount_received", "total_amount"):
        value[key] = str(value.get(key) or 0)
    for key in ("voucher_date", "created_at", "updated_at", "submitted_at"):
        if value.get(key) and hasattr(value[key], "isoformat"):
            value[key] = value[key].isoformat()
    return value


def products():
    return [
        {"code": code, "item": value["item"], "default_selling_price": str(value["default_selling_price"])}
        for code, value in voucher_engine.SOTEPHWAR_PRODUCTS.items()
    ]


def _customer_is_eligible(row):
    return bool(
        row and row.get("active") is True
        and row.get("customer_group") in {"SotePhwar", "Both"}
        and str(row.get("customer_name") or "").strip()
    )


def _snapshot_from_customer(row):
    if not row:
        return None
    snapshot = {key: row.get(key) for key in CUSTOMER_FIELDS}
    snapshot["id"] = int(snapshot["id"])
    for key in ("customer_name", "phone_number", "town", "contact_address"):
        snapshot[key] = str(snapshot.get(key) or "").strip()
    if snapshot.get("payment_terms_days") is not None:
        snapshot["payment_terms_days"] = int(snapshot["payment_terms_days"])
    snapshot["active"] = bool(snapshot.get("active"))
    return snapshot


def list_customers():
    with _connect() as connection, connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute(sql.SQL(
            'SELECT id,customer_name,"Customer_Code" AS customer_code,"Region" AS region,'
            'phone_number,town,contact_address,payment_terms_days,customer_group,active '
            'FROM {}.customer_master WHERE COALESCE(__nc_deleted,false)=false '
            "AND NULLIF(TRIM(customer_name),'') IS NOT NULL "
            "AND customer_group IN ('SotePhwar','Both') AND active IS TRUE ORDER BY customer_name,id"
        ).format(sql.Identifier(_schema())))
        return [dict(row) for row in cursor.fetchall() if _customer_is_eligible(row)]


def _load_customer_snapshot(customer_id, connection):
    if customer_id in (None, ""):
        return {}
    with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute(sql.SQL(
            'SELECT id,customer_name,phone_number,town,contact_address,payment_terms_days,customer_group,active '
            'FROM {}.customer_master WHERE id=%s AND COALESCE(__nc_deleted,false)=false '
            "AND customer_group IN ('SotePhwar','Both') AND active IS TRUE"
        ).format(sql.Identifier(_schema())), (int(customer_id),))
        snapshot = _snapshot_from_customer(cursor.fetchone())
    if not snapshot:
        raise voucher_engine.VoucherValidationError(["active SotePhwar/Both Customer Master record not found"])
    return snapshot


def _draft_customer_snapshot(values, current, connection):
    customer_id = (values or {}).get("customer_id")
    if customer_id in (None, ""):
        return {}
    existing = (current or {}).get("customer_snapshot") or {}
    if existing and int((current or {}).get("customer_id") or 0) == int(customer_id):
        return existing
    return _load_customer_snapshot(customer_id, connection)


def list_drafts(limit=50):
    with _connect() as connection, connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute(sql.SQL(
            "SELECT * FROM {}.{} WHERE sector='sotephwar' AND status<>'submitted' AND is_deleted=false ORDER BY updated_at DESC LIMIT %s"
        ).format(sql.Identifier(_schema()), sql.Identifier(DRAFT_TABLE)), (max(1, min(int(limit), 100)),))
        return [_payload(row) for row in cursor.fetchall()]


def get_draft(draft_id, connection=None, for_update=False):
    owns = connection is None
    connection = connection or _connect()
    try:
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(sql.SQL(
                "SELECT * FROM {}.{} WHERE id=%s AND sector='sotephwar' AND is_deleted=false{}"
            ).format(sql.Identifier(_schema()), sql.Identifier(DRAFT_TABLE), sql.SQL(" FOR UPDATE" if for_update else "")), (int(draft_id),))
            return _payload(cursor.fetchone())
    finally:
        if owns:
            connection.close()


def create_draft(values, created_by):
    draft = voucher_engine.new_draft("sotephwar")
    draft.update(values or {})
    draft["sector"] = "sotephwar"
    with _connect() as connection, connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        snapshot = _draft_customer_snapshot(draft, None, connection)
        draft["customer_name"] = snapshot.get("customer_name", "")
        cursor.execute(sql.SQL(
            "INSERT INTO {}.{} (sector,status,voucher_number,voucher_date,customer_id,customer_name,customer_snapshot,"
            "payment_method,note,amount_received,lines,delivery_sections,voucher_metadata,total_amount,created_by) "
            "VALUES ('sotephwar','draft',%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s::jsonb,'[]'::jsonb,%s::jsonb,0,%s) RETURNING *"
        ).format(sql.Identifier(_schema()), sql.Identifier(DRAFT_TABLE)), (
            str(draft.get("voucher_number") or ""), draft.get("voucher_date"), draft.get("customer_id"),
            draft["customer_name"], json.dumps(snapshot), str(draft.get("payment_method") or ""),
            str(draft.get("note") or ""), draft.get("amount_received") or 0,
            json.dumps(draft.get("lines") or [], default=_json_value), json.dumps({"discount_amount": draft.get("discount_amount", 0), "cashback_amount": draft.get("cashback_amount", 0), "adjustment_reason": draft.get("adjustment_reason", ""), "free_lines": draft.get("free_lines") or []}), created_by,
        ))
        row = cursor.fetchone()
        connection.commit()
        return _payload(row)


def update_draft(draft_id, values, expected_version):
    current = get_draft(draft_id)
    if not current:
        raise LookupError("SotePhwar voucher draft not found")
    if current["status"] == "submitted":
        raise ValueError("Submitted vouchers cannot be edited")
    merged = {**current, **(values or {}), "sector": "sotephwar"}
    with _connect() as connection, connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        snapshot = _draft_customer_snapshot(merged, current, connection)
        merged["customer_name"] = snapshot.get("customer_name", "")
        cursor.execute(sql.SQL(
            "UPDATE {}.{} SET status='draft',voucher_number=%s,voucher_date=%s,customer_id=%s,customer_name=%s,"
            "customer_snapshot=%s::jsonb,payment_method=%s,note=%s,amount_received=%s,lines=%s::jsonb,voucher_metadata=%s::jsonb,total_amount=0,"
            "version=version+1,updated_at=now() WHERE id=%s AND sector='sotephwar' AND version=%s RETURNING *"
        ).format(sql.Identifier(_schema()), sql.Identifier(DRAFT_TABLE)), (
            str(merged.get("voucher_number") or ""), merged.get("voucher_date"), merged.get("customer_id"),
            merged["customer_name"], json.dumps(snapshot), str(merged.get("payment_method") or ""),
            str(merged.get("note") or ""), merged.get("amount_received") or 0,
            json.dumps(merged.get("lines") or [], default=_json_value), json.dumps({"discount_amount": merged.get("discount_amount", 0), "cashback_amount": merged.get("cashback_amount", 0), "adjustment_reason": merged.get("adjustment_reason", ""), "free_lines": merged.get("free_lines") or []}), int(draft_id), int(expected_version),
        ))
        row = cursor.fetchone()
        if not row:
            raise RuntimeError("Draft changed in another session; refresh and retry")
        connection.commit()
        return _payload(row)


def set_workflow_state(draft_id, state):
    draft = get_draft(draft_id)
    if not draft:
        raise LookupError("SotePhwar voucher draft not found")
    normalized = voucher_engine.preview_sotephwar(draft) if state == "previewed" else voucher_engine.validate_sotephwar(draft)
    with _connect() as connection, connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute(sql.SQL(
            "UPDATE {}.{} SET status=%s,total_amount=%s,amount_received=%s,lines=%s::jsonb,voucher_metadata=%s::jsonb,updated_at=now(),version=version+1 "
            "WHERE id=%s AND sector='sotephwar' AND status<>'submitted' RETURNING *"
        ).format(sql.Identifier(_schema()), sql.Identifier(DRAFT_TABLE)), (
            state, normalized.get("total_amount", 0), normalized.get("amount_received", draft.get("amount_received", 0)),
            json.dumps(normalized["lines"], default=_json_value), json.dumps({"discount_amount": normalized["discount_amount"], "cashback_amount": normalized["cashback_amount"], "adjustment_reason": normalized["adjustment_reason"], "free_lines": normalized["free_lines"]}, default=_json_value), int(draft_id),
        ))
        row = cursor.fetchone()
        if not row:
            raise ValueError("Submitted vouchers cannot change workflow state")
        connection.commit()
    return {"draft": _payload(row), "voucher": normalized}


def _prepare_final_pdf(draft_id, voucher, pdf_directory=None):
    directory = Path(pdf_directory or SUBMITTED_PDF_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    number = "".join(ch for ch in str(voucher["voucher_number"]) if ch.isalnum() or ch in "-_")
    final_path = directory / f"SotePhwar_Voucher_{number}_draft_{int(draft_id)}.pdf"
    handle = tempfile.NamedTemporaryFile(dir=directory, prefix=".sotephwar-voucher-", suffix=".pdf", delete=False)
    temporary_path = Path(handle.name)
    handle.close()
    try:
        write_sotephwar_voucher_pdf(voucher, temporary_path)
        if not temporary_path.exists() or temporary_path.stat().st_size == 0:
            raise RuntimeError("Final SotePhwar Voucher PDF generation produced an empty file")
        checksum = hashlib.sha256(temporary_path.read_bytes()).hexdigest()
        temporary_path.replace(final_path)
        return final_path.resolve(), checksum
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def submitted_pdf_path(draft):
    path = Path(str((draft or {}).get("submitted_pdf_path") or ""))
    checksum = str((draft or {}).get("submitted_pdf_checksum") or "")
    if not checksum or not path.is_file():
        raise RuntimeError("Submitted voucher PDF metadata is unavailable")
    if hashlib.sha256(path.read_bytes()).hexdigest() != checksum:
        raise RuntimeError("Submitted voucher PDF checksum verification failed")
    return path


def submit(draft_id, submitted_by, connection=None, commit=True, pdf_directory=None):
    """Insert every line and customer link atomically; never touch inventory."""
    owns_connection = connection is None
    connection = connection or _connect()
    if owns_connection:
        connection.set_session(isolation_level="SERIALIZABLE", autocommit=False)
    prepared_pdf = None
    try:
        draft = get_draft(draft_id, connection=connection, for_update=True)
        if not draft:
            raise LookupError("SotePhwar voucher draft not found")
        if draft["status"] == "submitted":
            return {
                "draft": draft, "transaction_ids": draft.get("submitted_transaction_ids") or [], "idempotent": True,
                "pdf_path": draft.get("submitted_pdf_path"), "pdf_checksum": draft.get("submitted_pdf_checksum"),
            }
        if draft["status"] not in {"validated", "previewed"}:
            raise voucher_engine.VoucherValidationError(["voucher must be successfully validated before submit"])
        voucher = voucher_engine.preview_sotephwar(draft)
        rows = voucher_engine.sotephwar_transaction_rows(voucher)
        if not draft.get("customer_id"):
            raise voucher_engine.VoucherValidationError(["customer_id is required for submit"])
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            identity = f'SotePhwar|{voucher["voucher_number"]}|{voucher["voucher_date"]}|{voucher["customer_name"]}'
            cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (identity,))
            cursor.execute(sql.SQL(
                'SELECT id FROM {}."Sotephwar_Transection" WHERE COALESCE(__nc_deleted,false)=false '
                'AND "Invoice_Number"=%s AND "Invoice_Date"=%s AND COALESCE("Customer_Name",\'\')=%s LIMIT 1'
            ).format(sql.Identifier(_schema())), (voucher["voucher_number"], voucher["voucher_date"], voucher["customer_name"]))
            if cursor.fetchone():
                raise ValueError("A SotePhwar voucher with this number, date, and customer already exists")
            cursor.execute(sql.SQL(
                'SELECT id FROM {}.customer_master WHERE id=%s AND COALESCE(__nc_deleted,false)=false '
                "AND customer_group IN ('SotePhwar','Both') AND active IS TRUE FOR SHARE"
            ).format(sql.Identifier(_schema())), (int(draft["customer_id"]),))
            if not cursor.fetchone():
                raise ValueError("Selected active SotePhwar/Both Customer Master no longer exists")
            prepared_pdf = _prepare_final_pdf(draft_id, voucher, pdf_directory)

            # Free items remain immutable voucher metadata only. A future explicitly
            # approved Voucher -> Inventory workflow will own any stock movement.
            transaction_ids = []
            for row in rows:
                cursor.execute(sql.SQL(
                    'INSERT INTO {}."Sotephwar_Transection" ("Invoice_Number","Invoice_Date","Customer_Name","Item",'
                    '"Quantity","Total_Amount","Total_Received","Outstanding_Balance","Payment_Status","Note") '
                    'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id'
                ).format(sql.Identifier(_schema())), (
                    row["Invoice_Number"], row["Invoice_Date"], row["Customer_Name"], row["Item"], row["Quantity"],
                    row["Total_Amount"], row["Total_Received"], row["Outstanding_Balance"], row["Payment_Status"], row["Note"],
                ))
                transaction_id = cursor.fetchone()["id"]
                transaction_ids.append(transaction_id)
                cursor.execute(sql.SQL(
                    'INSERT INTO {}."_nc_m2m_Sotephwar_Trans_customer_master" '
                    '(customer_master_id,"Sotephwar_Transection_id") VALUES (%s,%s)'
                ).format(sql.Identifier(_schema())), (int(draft["customer_id"]), transaction_id))

            submitted_voucher = deepcopy(voucher)
            submitted_voucher.update({
                "status": "submitted", "submitted_transaction_ids": transaction_ids,
                "submitted_rows": rows, "submitted_by": submitted_by,
            })
            cursor.execute(sql.SQL(
                "UPDATE {}.{} SET status='submitted',total_amount=%s,submitted_transaction_id=%s,"
                "submitted_transaction_ids=%s::jsonb,submitted_voucher=%s::jsonb,submitted_pdf_path=%s,"
                "submitted_pdf_checksum=%s,submitted_at=now(),updated_at=now(),version=version+1 WHERE id=%s RETURNING *"
            ).format(sql.Identifier(_schema()), sql.Identifier(DRAFT_TABLE)), (
                voucher["total_amount"], transaction_ids[0], json.dumps(transaction_ids),
                json.dumps(submitted_voucher, default=_json_value), str(prepared_pdf[0]), prepared_pdf[1], int(draft_id),
            ))
            saved = _payload(cursor.fetchone())
        if commit:
            connection.commit()
        return {
            "draft": saved, "transaction_ids": transaction_ids, "idempotent": False,
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
    return draft_management.remove_draft(DRAFT_TABLE, draft_id, removed_by, reason, "sotephwar", connection, commit)


def delete_submitted_voucher(draft_id, voucher_number, reason, deleted_by, connection=None, commit=True):
    """Permanently remove one confirmed SotePhwar submission and its own rows.

    This administrative operation is intentionally separate from draft removal.
    It refuses vouchers with payment history and never touches customer, inventory,
    Formula Engine, or unrelated voucher records.
    """
    confirmed_number = str(voucher_number or "").strip()
    deletion_reason = str(reason or "").strip()
    if not confirmed_number:
        raise ValueError("Type the voucher number to confirm deletion")
    if not deletion_reason:
        raise ValueError("Deletion reason is required")

    owns_connection = connection is None
    connection = connection or _connect()
    if owns_connection:
        connection.set_session(isolation_level="SERIALIZABLE", autocommit=False)
    try:
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(sql.SQL(
                "SELECT * FROM {}.{} WHERE id=%s AND sector='sotephwar' FOR UPDATE"
            ).format(sql.Identifier(_schema()), sql.Identifier(DRAFT_TABLE)), (int(draft_id),))
            draft = cursor.fetchone()
            if not draft:
                raise LookupError("Submitted SotePhwar voucher not found")
            if draft.get("status") != "submitted" or draft.get("is_deleted"):
                raise ValueError("Only active submitted vouchers can be deleted here")
            actual_number = str(draft.get("voucher_number") or "")
            if confirmed_number != actual_number:
                raise ValueError("Voucher number confirmation does not match")

            cursor.execute(sql.SQL(
                'SELECT COUNT(*) AS count FROM {}."Payment_Receive" '
                'WHERE "Sector"=\'Sote Phwar\' AND "Voucher_Number"=%s '
                'AND "Customer"=%s AND ("Invoice_Date"=%s OR "Invoice_Date" IS NULL)'
            ).format(sql.Identifier(_schema())), (
                actual_number, draft.get("customer_name") or "", draft.get("voucher_date"),
            ))
            if int(cursor.fetchone()["count"] or 0):
                raise ValueError("Voucher has payment history and cannot be deleted")

            transaction_ids = [int(value) for value in draft.get("submitted_transaction_ids") or []]
            legacy_id = draft.get("submitted_transaction_id")
            if legacy_id and int(legacy_id) not in transaction_ids:
                transaction_ids.append(int(legacy_id))

            if transaction_ids:
                cursor.execute(sql.SQL(
                    'DELETE FROM {}."_nc_m2m_Sotephwar_Trans_customer_master" '
                    'WHERE "Sotephwar_Transection_id"=ANY(%s)'
                ).format(sql.Identifier(_schema())), (transaction_ids,))
                cursor.execute(sql.SQL(
                    'DELETE FROM {}."Sotephwar_Transection" WHERE id=ANY(%s)'
                ).format(sql.Identifier(_schema())), (transaction_ids,))

            cursor.execute(sql.SQL(
                "DELETE FROM {}.{} WHERE id=%s AND sector='sotephwar' AND status='submitted' RETURNING id"
            ).format(sql.Identifier(_schema()), sql.Identifier(DRAFT_TABLE)), (int(draft_id),))
            if not cursor.fetchone():
                raise RuntimeError("Voucher changed concurrently; refresh and retry")
        if commit:
            connection.commit()
        return {
            "deleted": True,
            "draft_id": int(draft_id),
            "voucher_number": actual_number,
            "customer_name": draft.get("customer_name") or "",
            "transaction_ids": transaction_ids,
            "pdf_path": draft.get("submitted_pdf_path"),
            "deleted_by": str(deleted_by or "Business OS"),
            "reason": deletion_reason,
        }
    except Exception:
        connection.rollback()
        raise
    finally:
        if owns_connection:
            connection.close()


def _history_quantity(lines):
    """Format history quantities safely, including JSON values such as '1000.00'."""
    total = sum((Decimal(str(line.get("quantity") or 0)) for line in lines), Decimal("0"))
    return int(total) if total == total.to_integral_value() else format(total.normalize(), "f")


def recent_submissions(filters=None, page=1, page_size=20):
    filters=filters or {}; page,page_size,offset=draft_management.paging(page,page_size)
    clauses=["d.sector='sotephwar'","d.status='submitted'","d.is_deleted=false","jsonb_array_length(d.submitted_transaction_ids)>0"]
    params={"limit":page_size,"offset":offset}
    for key,column in (("date_from","d.voucher_date>="),("date_to","d.voucher_date<="),("customer","d.customer_name ILIKE"),("voucher_number","d.voucher_number=")):
        value=filters.get(key)
        if value: params[key]=f"%{value}%" if key=="customer" else value; clauses.append(f"{column}%({key})s")
    if filters.get("payment_status"):
        params["payment_status"]=filters["payment_status"]; clauses.append("d.submitted_voucher->>'payment_status'=%(payment_status)s")
    where=" AND ".join(clauses)
    with _connect() as connection,connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute(sql.SQL('SELECT d.id AS draft_id,d.voucher_number,d.voucher_date,d.customer_name,d.submitted_at,'
            'd.submitted_transaction_ids,d.submitted_voucher,d.submitted_pdf_path,d.submitted_pdf_checksum,COUNT(*) OVER() total_count '
            'FROM {}.{} d WHERE '+where+' ORDER BY d.submitted_at DESC,d.id DESC LIMIT %(limit)s OFFSET %(offset)s').format(
            sql.Identifier(_schema()),sql.Identifier(DRAFT_TABLE)),params)
        rows=[dict(row) for row in cursor.fetchall()]
    total=int(rows[0].pop("total_count")) if rows else 0
    records=[]
    for row in rows:
        voucher=row.pop("submitted_voucher") or {}; lines=voucher.get("paid_lines") or voucher.get("lines") or []; free_lines=voucher.get("free_lines") or []
        previous_total=voucher.get("total_amount") or 0
        record_ids = row.pop("submitted_transaction_ids")
        pdf_path = row.pop("submitted_pdf_path", None)
        pdf_checksum = row.pop("submitted_pdf_checksum", None)
        records.append({**row,"voucher_date":row["voucher_date"].isoformat(),"submitted_at":row["submitted_at"].isoformat() if row["submitted_at"] else None,
            "product_summary":", ".join(str(line.get("item") or line.get("product_code") or "") for line in lines),
            "paid_quantity":_history_quantity(lines),
            "free_quantity":_history_quantity(free_lines),
            "gross_amount":str(voucher.get("gross_amount",previous_total) or 0),
            "discount_amount":str(voucher.get("discount_amount",0) or 0),
            "cashback_amount":str(voucher.get("cashback_amount",0) or 0),
            "net_amount":str(voucher.get("net_amount",previous_total) or 0),
            "total_quantity":_history_quantity(lines),"total_amount":str(previous_total),
            "total_received":str(voucher.get("amount_received") or 0),"outstanding_balance":str(voucher.get("outstanding_balance") or 0),
            "payment_status":voucher.get("payment_status") or "Outstanding","record_ids":record_ids,
            "pdf_available":bool(pdf_path and pdf_checksum)})
    return {"items":records,"records":records,"page":page,"page_size":page_size,"total":total,"pages":max(1,(total+page_size-1)//page_size)}


def submission_details(draft_id):
    with _connect() as connection,connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute(sql.SQL("SELECT * FROM {}.{} WHERE id=%s AND sector='sotephwar' AND status='submitted' AND is_deleted=false").format(
            sql.Identifier(_schema()),sql.Identifier(DRAFT_TABLE)),(int(draft_id),)); row=cursor.fetchone()
        if not row: raise LookupError("Submitted SotePhwar voucher not found")
        value=_payload(row)
        pdf_path = value.pop("submitted_pdf_path", None)
        pdf_checksum = value.pop("submitted_pdf_checksum", None)
        value["pdf_available"] = bool(pdf_path and pdf_checksum)
        ids=[int(x) for x in value.get("submitted_transaction_ids") or []]
        cursor.execute(sql.SQL('SELECT id,"Item" AS item,"Quantity" AS quantity,"Total_Amount" AS total_amount,'
            '"Total_Received" AS total_received,"Outstanding_Balance" AS outstanding_balance,"Payment_Status" AS payment_status '
            'FROM {}."Sotephwar_Transection" WHERE id=ANY(%s) ORDER BY id').format(sql.Identifier(_schema())),(ids,))
        value["transaction_rows"]=[dict(x) for x in cursor.fetchall()]
        return value


def operational_summary():
    with _connect() as connection,connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute(sql.SQL('SELECT COUNT(*) FILTER (WHERE status<>\'submitted\' AND is_deleted=false) open_drafts,'
            'COUNT(*) FILTER (WHERE status=\'submitted\' AND submitted_at::date=CURRENT_DATE) submitted_today,'
            'COALESCE(SUM(total_amount) FILTER (WHERE status=\'submitted\' AND submitted_at::date=CURRENT_DATE),0) total_today,'
            'COALESCE(SUM((submitted_voucher->>\'outstanding_balance\')::numeric) FILTER '
            '(WHERE status=\'submitted\' AND submitted_at::date=CURRENT_DATE),0) outstanding_today '
            'FROM {}.{} WHERE sector=\'sotephwar\'').format(sql.Identifier(_schema()),sql.Identifier(DRAFT_TABLE)))
        return dict(cursor.fetchone())
