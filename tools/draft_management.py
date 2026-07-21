"""Shared protected soft-removal and paging helpers for Business OS drafts."""
import psycopg2.extras
from psycopg2 import sql

import config
from tools.formula_engine import _connect


PAGE_SIZES = (20, 50, 100)


def paging(page=1, page_size=20):
    page = max(1, int(page or 1)); page_size = int(page_size or 20)
    if page_size not in PAGE_SIZES: raise ValueError("page_size must be 20, 50, or 100")
    return page, page_size, (page - 1) * page_size


def remove_draft(table, draft_id, removed_by, reason="", sector=None, connection=None, commit=True):
    owns = connection is None; connection = connection or _connect()
    if owns: connection.set_session(isolation_level="SERIALIZABLE", autocommit=False)
    try:
        where = sql.SQL("id=%s")
        params = [int(draft_id)]
        if sector:
            where += sql.SQL(" AND sector=%s"); params.append(sector)
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(sql.SQL("SELECT * FROM {}.{} WHERE {} FOR UPDATE").format(
                sql.Identifier(config.TRANSACTION_SCHEMA), sql.Identifier(table), where), params)
            row = cursor.fetchone()
            if not row: raise LookupError("Draft not found")
            if row.get("is_deleted"):
                if commit: connection.commit()
                return {"draft_id": int(draft_id), "removed": True, "idempotent": True}
            protected = bool(
                row.get("status") == "submitted" or row.get("submitted_transaction_id")
                or row.get("submitted_transaction_ids") or row.get("submitted_movement_id")
                or row.get("submitted_pdf_path") or row.get("submitted_pdf_checksum")
                or row.get("submitted_voucher") or row.get("submitted_json")
            )
            if protected: raise ValueError("Submitted or production-linked drafts cannot be removed")
            previous = row.get("status") or "draft"
            cursor.execute(sql.SQL(
                "UPDATE {}.{} SET is_deleted=true,deleted_at=now(),deleted_by=%s,deletion_reason=%s,"
                "deletion_previous_status=%s,updated_at=now(),version=version+1 WHERE id=%s AND is_deleted=false RETURNING id"
            ).format(sql.Identifier(config.TRANSACTION_SCHEMA), sql.Identifier(table)),
            (removed_by, str(reason or "").strip(), previous, int(draft_id)))
            if not cursor.fetchone(): raise RuntimeError("Draft changed concurrently; refresh and retry")
        if commit: connection.commit()
        return {"draft_id": int(draft_id), "removed": True, "idempotent": False, "previous_status": previous}
    except Exception:
        connection.rollback(); raise
    finally:
        if owns: connection.close()
