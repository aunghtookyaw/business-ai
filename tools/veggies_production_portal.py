"""Browser-first Veggies Production Basic routes and database operations."""

from __future__ import annotations

import json
import uuid
from datetime import date
from decimal import Decimal
from html import escape
from typing import Any

import psycopg2.extras
from flask import redirect, request, url_for

import config
from tools import formula_engine
from tools.veggies_production import CropDefinition, load_crop_definitions, parse_production_date, parse_quantity


def _ref(table: str) -> str:
    schema = config.TRANSACTION_SCHEMA.replace('"', '""')
    return f'"{schema}"."{table}"'


def _connect():
    return formula_engine._connect()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _date_text(value: Any) -> str:
    if isinstance(value, (date,)):
        return value.isoformat()
    return _text(value)


def _quantity_text(value: Any) -> str:
    if value is None or (isinstance(value, str) and not value.strip()):
        return ""
    return format(Decimal(str(value)), "f")


def _crop_field(crop: CropDefinition) -> str:
    return f"crop_{crop.crop_code}"


def portal_crops() -> list[CropDefinition]:
    """Return one active browser field per crop while importer aliases remain intact."""
    unique = {}
    for crop in load_crop_definitions():
        unique.setdefault(crop.crop_code, crop)
    return list(unique.values())


def validate_submission(values: dict[str, Any], crops: list[CropDefinition]) -> tuple[dict[str, Any], dict[str, str]]:
    """Validate a browser submission while preserving blank versus zero."""
    errors: dict[str, str] = {}
    try:
        production_date = parse_production_date(values.get("production_date"))
        if production_date is None:
            raise ValueError("Production Date is required.")
    except ValueError as exc:
        production_date = None
        errors["production_date"] = str(exc)

    entry_text = _text(values.get("entry_date"))
    try:
        entry_date = parse_production_date(entry_text, "Date of Entry") if entry_text else date.today()
    except ValueError as exc:
        entry_date = None
        errors["entry_date"] = str(exc)

    items = []
    for crop in crops:
        field = _crop_field(crop)
        try:
            quantity = parse_quantity(values.get(field), crop.crop_name)
        except ValueError as exc:
            errors[field] = str(exc)
            continue
        if quantity is not None:
            items.append({
                "crop_id": crop.crop_id,
                "crop_code": crop.crop_code,
                "crop_name": crop.crop_name,
                "quantity": quantity,
                "unit": crop.default_unit,
            })
    if not items and not any(key.startswith("crop_") for key in errors):
        errors["crops"] = "Enter at least one vegetable quantity. Zero is allowed."

    return {
        "production_date": production_date,
        "assignee": _text(values.get("assignee")) or None,
        "note": _text(values.get("note")) or None,
        "ai_note": _text(values.get("ai_note")) or None,
        "entry_date": entry_date,
        "submission_token": _text(values.get("submission_token")) or str(uuid.uuid4()),
        "items": items,
    }, errors


def save_submission(values: dict[str, Any], connection=None) -> dict[str, Any]:
    """Insert one batch and its normalized items in a single transaction."""
    owns_connection = connection is None
    connection = connection or _connect()
    try:
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(
                f"""
                INSERT INTO {_ref('veggies_production_batches')}
                  (production_date, assignee, note, ai_note, entry_date,
                   submission_token, created_by, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                ON CONFLICT (submission_token) WHERE submission_token IS NOT NULL DO NOTHING
                RETURNING id
                """,
                (values["production_date"], values["assignee"], values["note"],
                 values["ai_note"], values["entry_date"], values["submission_token"],
                 "Veggies Production Basic"),
            )
            row = cursor.fetchone()
            if not row:
                raise ValueError("This submission was already saved. Refresh before entering another record.")
            batch_id = row["id"]
            for item in values["items"]:
                cursor.execute(
                    f"""
                    INSERT INTO {_ref('veggies_production_items')}
                      (production_batch_id, crop_id, quantity, unit, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, NOW(), NOW())
                    """,
                    (batch_id, item["crop_id"], item["quantity"], item["unit"]),
                )
        connection.commit()
        return {"id": batch_id}
    except Exception:
        connection.rollback()
        raise
    finally:
        if owns_connection:
            connection.close()


def update_submission(batch_id: int, values: dict[str, Any], connection=None) -> dict[str, Any]:
    """Explicitly replace a batch's editable values and items in one transaction."""
    owns_connection = connection is None
    connection = connection or _connect()
    try:
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(
                f"SELECT id FROM {_ref('veggies_production_batches')} WHERE id = %s FOR UPDATE",
                (batch_id,),
            )
            if not cursor.fetchone():
                raise LookupError("Production record not found.")
            cursor.execute(
                f"""
                UPDATE {_ref('veggies_production_batches')}
                SET production_date=%s, assignee=%s, note=%s, ai_note=%s,
                    entry_date=%s, updated_at=NOW()
                WHERE id=%s
                """,
                (values["production_date"], values["assignee"], values["note"],
                 values["ai_note"], values["entry_date"], batch_id),
            )
            cursor.execute(
                f"DELETE FROM {_ref('veggies_production_items')} WHERE production_batch_id = %s",
                (batch_id,),
            )
            for item in values["items"]:
                cursor.execute(
                    f"""
                    INSERT INTO {_ref('veggies_production_items')}
                      (production_batch_id, crop_id, quantity, unit, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, NOW(), NOW())
                    """,
                    (batch_id, item["crop_id"], item["quantity"], item["unit"]),
                )
        connection.commit()
        return {"id": batch_id}
    except Exception:
        connection.rollback()
        raise
    finally:
        if owns_connection:
            connection.close()


def search_records(filters: dict[str, str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    conditions = ["TRUE"]
    params: list[Any] = []
    mappings = [
        ("date_from", "batch.production_date >= %s"),
        ("date_to", "batch.production_date <= %s"),
        ("production_date", "batch.production_date = %s"),
    ]
    for key, condition in mappings:
        if filters.get(key):
            conditions.append(condition)
            params.append(filters[key])
    if filters.get("assignee"):
        conditions.append("COALESCE(batch.assignee, '') ILIKE %s")
        params.append(f"%{filters['assignee']}%")
    if filters.get("crop"):
        conditions.append("crop.crop_code = %s")
        params.append(filters["crop"])
    if filters.get("min_quantity"):
        conditions.append("item.quantity >= %s")
        params.append(filters["min_quantity"])
    if filters.get("max_quantity"):
        conditions.append("item.quantity <= %s")
        params.append(filters["max_quantity"])
    if filters.get("note"):
        conditions.append("COALESCE(batch.note, '') ILIKE %s")
        params.append(f"%{filters['note']}%")
    where_sql = " AND ".join(conditions)
    query = f"""
      SELECT batch.id, batch.production_date, batch.assignee, batch.note, batch.entry_date,
             SUM(item.quantity) AS total_quantity, COUNT(DISTINCT item.crop_id) AS crop_count,
             batch.created_at, batch.updated_at
      FROM {_ref('veggies_production_batches')} batch
      JOIN {_ref('veggies_production_items')} item ON item.production_batch_id = batch.id
      JOIN {_ref('veggies_crop_master')} crop ON crop.id = item.crop_id
      WHERE {where_sql}
      GROUP BY batch.id
      ORDER BY batch.production_date DESC, batch.id DESC
      LIMIT 500
    """
    connection = _connect()
    try:
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(query, params)
            rows = [dict(row) for row in cursor.fetchall()]
        summaries = {
            "total_quantity": sum((row["total_quantity"] or Decimal("0") for row in rows), Decimal("0")),
            "submission_count": len(rows),
            "crop_count": 0,
            "latest_date": max((row["production_date"] for row in rows), default=None),
        }
        if rows:
            ids = [row["id"] for row in rows]
            with connection.cursor() as cursor:
                cursor.execute(
                    f"SELECT COUNT(DISTINCT crop_id) FROM {_ref('veggies_production_items')} WHERE production_batch_id = ANY(%s)",
                    (ids,),
                )
                summaries["crop_count"] = cursor.fetchone()[0]
        return rows, summaries
    finally:
        connection.close()


def get_record(batch_id: int) -> dict[str, Any] | None:
    connection = _connect()
    try:
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(
                f"SELECT * FROM {_ref('veggies_production_batches')} WHERE id=%s",
                (batch_id,),
            )
            batch = cursor.fetchone()
            if not batch:
                return None
            cursor.execute(
                f"""
                SELECT item.crop_id, crop.crop_code, crop.crop_name, item.quantity, item.unit,
                       item.created_at, item.updated_at
                FROM {_ref('veggies_production_items')} item
                JOIN {_ref('veggies_crop_master')} crop ON crop.id=item.crop_id
                WHERE item.production_batch_id=%s
                ORDER BY crop.display_order, crop.crop_name
                """,
                (batch_id,),
            )
            result = dict(batch)
            result["items"] = [dict(row) for row in cursor.fetchall()]
            return result
    finally:
        connection.close()


BASE_STYLE = """
body{margin:0;font-family:Arial,sans-serif;background:#f4f6f5;color:#17211c}header{padding:18px 22px;background:#fff;border-bottom:1px solid #ccd5d0}main{padding:16px;max-width:1600px;margin:auto}section{background:#fff;border:1px solid #d5ddd9;border-radius:8px;margin-bottom:16px;padding:16px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}.crop-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;max-height:420px;overflow:auto;padding:4px}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.card{background:#174f3b;color:white;border-radius:8px;padding:16px}.card strong{display:block;font-size:24px;margin-top:6px}label{display:block;font-weight:bold;font-size:12px;color:#47554e}input,textarea,select,button{box-sizing:border-box;width:100%;padding:9px;margin-top:5px;border:1px solid #aebbb5;border-radius:5px;font:inherit}button,.button{background:#176b5d;color:white;border:0;font-weight:bold;cursor:pointer;text-decoration:none;display:inline-block;padding:10px 16px;border-radius:5px;width:auto}.secondary{background:#fff;color:#176b5d;border:1px solid #176b5d}.error{color:#b00020;font-size:12px;margin-top:4px}.status{padding:12px;border-radius:6px;background:#e1f3ed;color:#155d4f;font-weight:bold}.status.bad{background:#fde8e8;color:#9b1c1c}.table-wrap{overflow:auto}table{width:100%;min-width:950px;border-collapse:collapse}th,td{padding:9px;border-bottom:1px solid #e1e6e3;text-align:left;white-space:nowrap}th{background:#edf2ef}.actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}.required{color:#a11}.original{background:#f8faf9;padding:12px;border-left:4px solid #d6a84b;margin-bottom:14px}@media(max-width:800px){.cards{grid-template-columns:1fr 1fr}.crop-grid{grid-template-columns:1fr 1fr}}@media(max-width:480px){.cards,.crop-grid{grid-template-columns:1fr}}
"""


def _error(errors: dict[str, str], field: str) -> str:
    return f'<div class="error">{escape(errors[field])}</div>' if field in errors else ""


def _entry_form(crops, values, errors, action, edit=False):
    fields = []
    item_values = values.get("item_values", {})
    for crop in crops:
        field = _crop_field(crop)
        value = values.get(field, item_values.get(crop.crop_code, ""))
        fields.append(f'''<label>{escape(crop.crop_name)}<input type="number" step="any" min="0" name="{field}" value="{escape(_quantity_text(value))}" inputmode="decimal">{_error(errors, field)}</label>''')
    confirm = '<label><input style="width:auto" type="checkbox" name="confirm_changes" value="yes" required> I reviewed the original values and confirm these changes.</label>' if edit else ""
    return f'''<form method="post" action="{escape(action)}" id="productionForm">
      <input type="hidden" name="submission_token" value="{escape(_text(values.get('submission_token')) or str(uuid.uuid4()))}">
      <div class="grid">
        <label>Production Date <span class="required">*</span><input type="date" name="production_date" value="{escape(_date_text(values.get('production_date')))}" required>{_error(errors,'production_date')}</label>
        <label>Assignee<input name="assignee" value="{escape(_text(values.get('assignee')))}"></label>
        <label>Date of Entry<input type="date" name="entry_date" value="{escape(_date_text(values.get('entry_date')) or date.today().isoformat())}">{_error(errors,'entry_date')}</label>
      </div>
      <h3>Vegetable quantities <span class="required">*</span></h3>{_error(errors,'crops')}
      <div class="crop-grid">{''.join(fields)}</div>
      <div class="grid">
        <label>Note<textarea name="note" rows="3">{escape(_text(values.get('note')))}</textarea></label>
        <label>AI Note<textarea name="ai_note" rows="3">{escape(_text(values.get('ai_note')))}</textarea></label>
      </div>{confirm}
      <div class="actions"><button id="saveButton" type="submit">{'Save Changes' if edit else 'Save Production'}</button></div>
    </form><script>document.getElementById('productionForm').addEventListener('submit',function(){{const b=document.getElementById('saveButton');b.disabled=true;b.textContent='Saving…';}});</script>'''


def _filters() -> dict[str, str]:
    return {key: _text(request.args.get(key)) for key in (
        "date_from", "date_to", "production_date", "assignee", "crop",
        "min_quantity", "max_quantity", "note",
    )}


def _render_main(crops, values=None, errors=None, message="", bad=False):
    values = values or {}
    errors = errors or {}
    filters = _filters()
    try:
        rows, summary = search_records(filters)
        load_error = ""
    except Exception as exc:
        rows, summary = [], {"total_quantity": 0, "submission_count": 0, "crop_count": 0, "latest_date": None}
        load_error = f"Could not load production records: {exc}"
    status = message or load_error
    status_html = f'<p class="status {"bad" if bad or load_error else ""}">{escape(status)}</p>' if status else ""
    crop_options = ''.join(f'<option value="{escape(c.crop_code)}" {"selected" if filters["crop"]==c.crop_code else ""}>{escape(c.crop_name)}</option>' for c in crops)
    result_rows = ''.join(
        f'<tr><td>{escape(_date_text(row["production_date"]))}</td><td>{escape(_text(row["assignee"]))}</td><td>{escape(_quantity_text(row["total_quantity"]))}</td><td>{row["crop_count"]}</td><td>{escape(_text(row["note"]))}</td><td>{escape(_date_text(row["entry_date"]))}</td><td><a href="/veggies-production/{row["id"]}">View Details</a></td></tr>'
        for row in rows
    ) or '<tr><td colspan="7">No production records found.</td></tr>'
    return f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Veggies Production Basic</title><style>{BASE_STYLE}</style></head><body>
    <header><h1>Veggies Production Basic</h1></header><main>{status_html}
    <div class="cards"><div class="card">Total Production Quantity<strong>{escape(_quantity_text(summary['total_quantity']))}</strong></div><div class="card">Production Submissions<strong>{summary['submission_count']}</strong></div><div class="card">Crops Produced<strong>{summary['crop_count']}</strong></div><div class="card">Latest Production Date<strong>{escape(_date_text(summary['latest_date']) or '—')}</strong></div></div>
    <section><h2>New production submission</h2>{_entry_form(crops, values, errors, '/veggies-production')}</section>
    <section><h2>Search and review</h2><form method="get" action="/veggies-production"><div class="grid">
      <label>Date From<input type="date" name="date_from" value="{escape(filters['date_from'])}"></label><label>Date To<input type="date" name="date_to" value="{escape(filters['date_to'])}"></label><label>Production Date<input type="date" name="production_date" value="{escape(filters['production_date'])}"></label><label>Assignee<input name="assignee" value="{escape(filters['assignee'])}"></label><label>Crop<select name="crop"><option value="">All crops</option>{crop_options}</select></label><label>Minimum Quantity<input type="number" step="any" min="0" name="min_quantity" value="{escape(filters['min_quantity'])}"></label><label>Maximum Quantity<input type="number" step="any" min="0" name="max_quantity" value="{escape(filters['max_quantity'])}"></label><label>Note search<input name="note" value="{escape(filters['note'])}"></label></div><div class="actions"><button type="submit">Search</button><a class="button secondary" href="/veggies-production">Clear</a></div></form>
      <div class="table-wrap"><table><thead><tr><th>Production Date</th><th>Assignee</th><th>Total Production Quantity</th><th>Number of Crops</th><th>Note</th><th>Date of Entry</th><th>Action</th></tr></thead><tbody>{result_rows}</tbody></table></div></section>
    </main></body></html>''', 200, {"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"}


def register_routes(app) -> None:
    @app.route("/veggies-production", methods=["GET", "POST"])
    def veggies_production_basic():
        try:
            crops = portal_crops()
        except Exception as exc:
            return _render_main([], message=f"Could not load crop master: {exc}", bad=True)
        if request.method == "GET":
            message = "Production saved." if request.args.get("saved") else ""
            return _render_main(crops, message=message)
        values = request.form.to_dict()
        cleaned, errors = validate_submission(values, crops)
        if errors:
            return _render_main(crops, values=values, errors=errors, message="Please correct the highlighted fields.", bad=True)
        try:
            result = save_submission(cleaned)
        except ValueError as exc:
            return _render_main(crops, values=values, message=str(exc), bad=True)
        except Exception:
            return _render_main(crops, values=values, message="Production could not be saved. No data was committed.", bad=True)
        return redirect(url_for("veggies_production_basic", saved="1", record=result["id"]), code=303)

    @app.get("/veggies-production/<int:batch_id>")
    def veggies_production_detail(batch_id):
        record = get_record(batch_id)
        if not record:
            return "Production record not found.", 404
        item_rows = ''.join(f'<tr><td>{escape(item["crop_name"])}</td><td>{escape(_quantity_text(item["quantity"]))}</td><td>{escape(_text(item["unit"]) or "—")}</td><td>{escape(_text(item["created_at"]))}</td><td>{escape(_text(item["updated_at"]))}</td></tr>' for item in record["items"])
        return f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Veggies Production Detail</title><style>{BASE_STYLE}</style></head><body><header><h1>Veggies Production Basic</h1></header><main><section><h2>Production record #{batch_id}</h2><div class="grid"><p><b>Production Date</b><br>{escape(_date_text(record['production_date']))}</p><p><b>Assignee</b><br>{escape(_text(record['assignee']) or '—')}</p><p><b>Date of Entry</b><br>{escape(_date_text(record['entry_date']) or '—')}</p><p><b>Created</b><br>{escape(_text(record['created_at']))}</p><p><b>Updated</b><br>{escape(_text(record['updated_at']))}</p></div><p><b>Note</b><br>{escape(_text(record['note']) or '—')}</p><p><b>AI Note</b><br>{escape(_text(record['ai_note']) or '—')}</p><div class="table-wrap"><table><thead><tr><th>Crop</th><th>Quantity</th><th>Unit</th><th>Created time</th><th>Updated time</th></tr></thead><tbody>{item_rows}</tbody></table></div><div class="actions"><a class="button" href="/veggies-production/{batch_id}/edit">Edit</a><a class="button secondary" href="/veggies-production">Back</a></div></section></main></body></html>'''

    @app.route("/veggies-production/<int:batch_id>/edit", methods=["GET", "POST"])
    def veggies_production_edit(batch_id):
        crops = portal_crops()
        record = get_record(batch_id)
        if not record:
            return "Production record not found.", 404
        known_codes = {crop.crop_code for crop in crops}
        for item in record["items"]:
            if item["crop_code"] not in known_codes:
                crops.append(CropDefinition(
                    item["crop_code"], item["crop_name"], item["crop_name"],
                    crop_id=item["crop_id"], default_unit=item["unit"],
                ))
        original = {
            **record,
            "item_values": {item["crop_code"]: item["quantity"] for item in record["items"]},
        }
        if request.method == "GET":
            values, errors, message = original, {}, ""
        else:
            values = request.form.to_dict()
            cleaned, errors = validate_submission(values, crops)
            if request.form.get("confirm_changes") != "yes":
                errors["confirm_changes"] = "Confirm the changes before saving."
            if not errors:
                try:
                    update_submission(batch_id, cleaned)
                except Exception:
                    return "Production changes could not be saved. No data was committed.", 500
                return redirect(f"/veggies-production/{batch_id}", code=303)
            message = "Please correct the highlighted fields."
        original_text = f"Original: {_date_text(record['production_date'])}; {record.get('assignee') or 'no assignee'}; {len(record['items'])} crops."
        return f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Edit Veggies Production</title><style>{BASE_STYLE}</style></head><body><header><h1>Veggies Production Basic</h1></header><main><section><h2>Edit production record #{batch_id}</h2><div class="original">{escape(original_text)} The saved record is not changed until you confirm and submit.</div>{f'<p class="status bad">{escape(message)}</p>' if message else ''}{_entry_form(crops, values, errors, f'/veggies-production/{batch_id}/edit', edit=True)}{_error(errors,'confirm_changes')}<div class="actions"><a class="button secondary" href="/veggies-production/{batch_id}">Cancel</a></div></section></main></body></html>'''
