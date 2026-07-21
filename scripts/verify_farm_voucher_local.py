"""Rollback-only live verification for the Farm Voucher submit path."""
import json
from pathlib import Path
import sys
import tempfile

import psycopg2.extras
from psycopg2 import sql

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
from tools.formula_engine import _connect
from tools import farm_voucher_repository, voucher_engine
from tools.farm_voucher_pdf import write_farm_voucher_pdf


VERIFY_VOUCHER = 999999999


def verify():
    schema = config.TRANSACTION_SCHEMA
    connection = _connect()
    connection.set_session(isolation_level="SERIALIZABLE", autocommit=False)
    result = {}
    try:
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute("SELECT id, crop_name, default_unit FROM public.veggies_crop_master WHERE active=TRUE ORDER BY display_order NULLS LAST,id LIMIT 1")
            crop = dict(cursor.fetchone())
            sections = [
                {"delivery_date": "2026-07-10", "items": [{"crop_id": crop["id"], "crop_name": crop["crop_name"], "quantity": "1", "unit": crop.get("default_unit") or "kg", "unit_price": "1000", "note": "first delivery"}]},
                {"delivery_date": "2026-07-12", "items": [{"crop_id": crop["id"], "crop_name": crop["crop_name"], "quantity": "1", "unit": crop.get("default_unit") or "kg", "unit_price": "2000", "note": "second price"}]},
            ]
            cursor.execute(
                sql.SQL(
                    "INSERT INTO {}.business_os_voucher_draft "
                    "(sector,status,voucher_number,voucher_date,customer_id,customer_name,payment_method,note,"
                    "customer_snapshot,amount_received,lines,delivery_sections,total_amount,created_by) VALUES "
                    "('farm','previewed',%s,CURRENT_DATE,90,'Ma Nge','Cash','Rollback-only verification',%s::jsonb,1000,'[]'::jsonb,%s::jsonb,3000,'local-verifier') RETURNING id"
                ).format(sql.Identifier(schema)),
                (str(VERIFY_VOUCHER), json.dumps({
                    "id": 90, "customer_name": "Ma Nge", "phone_number": "091234567",
                    "town": "Heho", "contact_address": "Rollback Farm Road",
                    "payment_terms_days": 30, "customer_group": "Farm", "active": True,
                }), json.dumps(sections, default=str)),
            )
            draft_id = cursor.fetchone()["id"]
        pdf_directory = tempfile.TemporaryDirectory()
        submitted = farm_voucher_repository.submit(
            draft_id, "local-verifier", connection=connection, commit=False,
            pdf_directory=pdf_directory.name,
        )
        transaction_id = submitted["transaction_id"]
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(
                sql.SQL(
                    'SELECT f.id,f."Date",f."Invoice_Number",f."Customer",f."Total_Amount",f."Total_Received",'
                    'f."Outstanding_Balance",f."Payment_Status",f."Note",f."AI_Analysis",l.customer_master_id '
                    'FROM {}.farm_transection f JOIN {}."_nc_m2m_farm_transectio_customer_master" l '
                    'ON l.farm_transection_id=f.id WHERE f.id=%s'
                ).format(sql.Identifier(schema), sql.Identifier(schema)),
                (transaction_id,),
            )
            row = dict(cursor.fetchone())
        draft = farm_voucher_repository.get_draft(draft_id, connection=connection)
        voucher = voucher_engine.preview({**draft, "delivery_sections": sections})
        pdf = farm_voucher_repository.submitted_pdf_path(draft)
        pdf_size = pdf.stat().st_size
        expected = {
            "Invoice_Number": VERIFY_VOUCHER, "Customer": "Ma Nge", "Total_Amount": "3000.00",
            "Total_Received": "1000.00", "Outstanding_Balance": "2000.00",
            "Payment_Status": "Partial", "customer_master_id": 90,
        }
        for key, value in expected.items():
            if str(row[key]) != str(value):
                raise RuntimeError(f"Submit verification mismatch for {key}: {row[key]} != {value}")
        if draft["status"] != "submitted" or draft["submitted_transaction_id"] != transaction_id:
            raise RuntimeError("Draft submit state verification failed")
        if row["Note"] is not None or row["AI_Analysis"] is not None:
            raise RuntimeError("Detailed voucher content leaked into farm_transection")
        submitted_json = draft.get("submitted_voucher") or {}
        if len(submitted_json.get("delivery_sections") or []) != 2:
            raise RuntimeError("Submitted structured voucher did not retain delivery sections")
        if submitted_json.get("customer_snapshot", {}).get("phone_number") != "091234567":
            raise RuntimeError("Submitted structured voucher did not retain customer snapshot")
        result = {"verified_inside_transaction": True, "delivery_dates": [section["delivery_date"] for section in voucher["delivery_sections"]], "transaction": row, "draft_status": draft["status"], "pdf_bytes": pdf_size}
    finally:
        connection.rollback()
        connection.close()
        if 'pdf_directory' in locals():
            pdf_directory.cleanup()

    with _connect() as check, check.cursor() as cursor:
        cursor.execute(
            sql.SQL('SELECT COUNT(*) FROM {}.farm_transection WHERE "Invoice_Number"=%s').format(sql.Identifier(schema)),
            (VERIFY_VOUCHER,),
        )
        remaining_transactions = cursor.fetchone()[0]
        cursor.execute(
            sql.SQL('SELECT COUNT(*) FROM {}.business_os_voucher_draft WHERE voucher_number=%s').format(sql.Identifier(schema)),
            (str(VERIFY_VOUCHER),),
        )
        remaining_drafts = cursor.fetchone()[0]
    if remaining_transactions or remaining_drafts:
        raise RuntimeError("Rollback-only verification left persistent rows")
    result.update({"rolled_back": True, "remaining_transactions": 0, "remaining_drafts": 0})
    return result


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2, default=str))
