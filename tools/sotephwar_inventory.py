"""Operational adapter for the existing Sotephwar_Inventory movement ledger."""
from copy import deepcopy
from datetime import date
from decimal import Decimal, InvalidOperation
import json
import re
from uuid import uuid4

import psycopg2.extras
from psycopg2 import sql

import config
from tools import formula_engine
from tools import draft_management


PRODUCTS = (
    "Sote Phwar 4L",
    "Sote Phwar 1L",
    "Sote Phwar 500 mL",
    "Sote Phwar 100 mL",
)
STORES = (
    "Factory",
    "Heho Store (Home)",
    "Min Hla Store",
    "Naung Tayar",
    "Tatkone Store",
)
MOVEMENT_TYPES = ("Production", "Transfer", "Sale")
SUBMISSION_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_-]{16,100}$")
SUBMISSION_MARKER = "Business OS inventory submission:"
DRAFT_TABLE = "business_os_inventory_movement_draft"


class InventoryValidationError(ValueError):
    def __init__(self, errors):
        self.errors = errors
        super().__init__("; ".join(errors))


def _text(value):
    return str(value or "").strip()


def authoritative_stock():
    """Call the Formula Engine's canonical stock calculation exactly once."""
    return formula_engine.sotephwar_inventory_stock(period="all_time").get("stock") or []


def inventory_summary():
    stock_rows = authoritative_stock()
    quantities = {(row.get("store"), row.get("product")): int(row.get("stock_qty") or 0) for row in stock_rows}
    matrix = []
    product_totals = []
    for product in PRODUCTS:
        stores = {store: quantities.get((store, product), 0) for store in STORES}
        total = sum(stores.values())
        matrix.append({"product": product, "stores": stores, "total": total})
        product_totals.append({"product": product, "quantity": total, "status": "zero" if total == 0 else "low" if total < 100 else "ok"})
    return {
        "formula": "sotephwar_inventory_stock",
        "unit": "bottles",
        "products": list(PRODUCTS),
        "stores": list(STORES),
        "total_stock": sum(row["quantity"] for row in product_totals),
        "product_totals": product_totals,
        "matrix": matrix,
    }


def available_stock(product, store):
    for row in authoritative_stock():
        if row.get("product") == product and row.get("store") == store:
            return int(row.get("stock_qty") or 0)
    return 0


def validate_movement(values, check_stock=True):
    movement = deepcopy(values or {})
    errors = []
    movement_type = _text(movement.get("type"))
    product = _text(movement.get("product"))
    from_store = _text(movement.get("from_store"))
    to_store = _text(movement.get("to_store"))
    note = _text(movement.get("note"))
    try:
        movement_date = date.fromisoformat(_text(movement.get("date"))).isoformat()
    except ValueError:
        movement_date = ""
        errors.append("Date is required and must use YYYY-MM-DD")
    if movement_type not in MOVEMENT_TYPES:
        errors.append("Type must be Production, Transfer or Sale")
    if product not in PRODUCTS:
        errors.append("Product is required and must use the fixed product list")
    try:
        quantity = Decimal(str(movement.get("quantity")))
    except (InvalidOperation, TypeError, ValueError):
        quantity = Decimal("0")
        errors.append("Quantity must be a number")
    if quantity <= 0:
        errors.append("Quantity must be positive")
    if quantity != quantity.to_integral_value():
        errors.append("Quantity must be a whole number of bottles")

    if movement_type == "Production":
        if from_store:
            errors.append("Production From Store must remain blank")
        if to_store not in STORES:
            errors.append("Production To Store is required")
    elif movement_type == "Transfer":
        if from_store not in STORES:
            errors.append("Transfer From Store is required")
        if to_store not in STORES:
            errors.append("Transfer To Store is required")
        if from_store and from_store == to_store:
            errors.append("Transfer From and To stores cannot be identical")
    elif movement_type == "Sale":
        if from_store not in STORES:
            errors.append("Sale From Store is required")
        if to_store:
            errors.append("Sale To Store must remain blank")

    available = None
    if not errors and check_stock and movement_type in {"Transfer", "Sale"}:
        available = available_stock(product, from_store)
        if int(quantity) > available:
            errors.append(f"Insufficient stock: {available} bottles available at {from_store}")
    if errors:
        raise InventoryValidationError(errors)
    return {
        "date": movement_date,
        "type": movement_type,
        "from_store": from_store,
        "to_store": to_store,
        "product": product,
        "quantity": int(quantity),
        "note": note,
        "available_stock": available,
    }


def movement_history(filters=None):
    filters = filters or {}
    product = _text(filters.get("product")) or None
    store = _text(filters.get("store")) or None
    movement_type = _text(filters.get("type")) or None
    if product and product not in PRODUCTS:
        raise InventoryValidationError(["Invalid product filter"])
    if store and store not in STORES:
        raise InventoryValidationError(["Invalid store filter"])
    if movement_type and movement_type not in MOVEMENT_TYPES:
        raise InventoryValidationError(["Invalid type filter"])
    result = formula_engine.sotephwar_inventory_list(
        period="all_time", product=product, store=store,
        movement_type=movement_type, limit=500,
    )
    search = _text(filters.get("search")).casefold()
    date_filter = _text(filters.get("date"))
    rows = []
    for source in result.get("movements") or []:
        row = dict(source)
        if row.get("date") and hasattr(row["date"], "isoformat"):
            row["date"] = row["date"].isoformat()
        haystack = " ".join(_text(row.get(key)) for key in ("type", "from_store", "to_store", "product", "note")).casefold()
        if search and search not in haystack:
            continue
        if date_filter and _text(row.get("date")) != date_filter:
            continue
        rows.append(row)
    return {"movements": rows, "count": len(rows), "filters": {"search": search, "date": date_filter, "type": movement_type, "product": product, "store": store}}


def submit_movement(values, connection=None, commit=True):
    submission_key = _text((values or {}).get("submission_key"))
    if not SUBMISSION_KEY_PATTERN.fullmatch(submission_key):
        raise InventoryValidationError(["A valid submission key is required"])
    if (values or {}).get("confirmed") is not True:
        raise InventoryValidationError(["Movement confirmation is required"])
    movement = validate_movement(values, check_stock=False)
    owns = connection is None
    connection = connection or formula_engine._connect()
    if owns:
        connection.set_session(isolation_level="SERIALIZABLE", autocommit=False)
    marker = f"{SUBMISSION_MARKER}{submission_key}"
    try:
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (f"SotephwarInventory|{movement['product']}|{movement['from_store']}",))
            cursor.execute(sql.SQL('SELECT id FROM {}."Sotephwar_Inventory" WHERE "AI_comment"=%s LIMIT 1').format(sql.Identifier(config.TRANSACTION_SCHEMA)), (marker,))
            existing = cursor.fetchone()
            if existing:
                if commit:
                    connection.commit()
                return {"movement_id": int(existing["id"]), "idempotent": True, "movement": movement, "stock": inventory_summary()}
            movement = validate_movement(movement, check_stock=True)
            cursor.execute(sql.SQL(
                'INSERT INTO {}."Sotephwar_Inventory" ("Date","Type","From_Store","To_Store","Product","Qty","AI_comment","Note") '
                'VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id'
            ).format(sql.Identifier(config.TRANSACTION_SCHEMA)), (
                movement["date"], movement["type"], movement["from_store"] or None,
                movement["to_store"] or None, movement["product"], movement["quantity"], marker, movement["note"] or None,
            ))
            movement_id = int(cursor.fetchone()["id"])
        if commit:
            connection.commit()
        return {"movement_id": movement_id, "idempotent": False, "movement": movement, "stock": inventory_summary() if commit else None}
    except Exception:
        connection.rollback()
        raise
    finally:
        if owns:
            connection.close()


def _draft_payload(row):
    if not row: return None
    value=dict(row)
    for key in ("movement_date","created_at","updated_at","submitted_at","deleted_at"):
        if value.get(key) and hasattr(value[key],"isoformat"): value[key]=value[key].isoformat()
    if value.get("submission_key"): value["submission_key"]=str(value["submission_key"])
    value["quantity"]=int(value.get("quantity") or 0)
    return value


def list_drafts(limit=50):
    with formula_engine._connect() as connection,connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute(sql.SQL("SELECT * FROM {}.{} WHERE status<>'submitted' AND is_deleted=false ORDER BY updated_at DESC LIMIT %s").format(
            sql.Identifier(config.TRANSACTION_SCHEMA),sql.Identifier(DRAFT_TABLE)),(max(1,min(int(limit),100)),))
        return [_draft_payload(row) for row in cursor.fetchall()]


def get_draft(draft_id,connection=None,for_update=False):
    owns=connection is None; connection=connection or formula_engine._connect()
    try:
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(sql.SQL('SELECT * FROM {}.{} WHERE id=%s AND is_deleted=false{}').format(
                sql.Identifier(config.TRANSACTION_SCHEMA),sql.Identifier(DRAFT_TABLE),sql.SQL(" FOR UPDATE" if for_update else "")),(int(draft_id),))
            return _draft_payload(cursor.fetchone())
    finally:
        if owns: connection.close()


def create_draft(values,created_by):
    values=values or {}
    with formula_engine._connect() as connection,connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute(sql.SQL('INSERT INTO {}.{} (submission_key,movement_date,movement_type,product,from_store,to_store,quantity,note,created_by) '
            'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *').format(sql.Identifier(config.TRANSACTION_SCHEMA),sql.Identifier(DRAFT_TABLE)),(
            uuid4(),values.get("date") or date.today(),_text(values.get("type")),_text(values.get("product")),_text(values.get("from_store")),
            _text(values.get("to_store")),int(values.get("quantity") or 0),_text(values.get("note")),created_by))
        row=cursor.fetchone();connection.commit();return _draft_payload(row)


def update_draft(draft_id,values,expected_version):
    current=get_draft(draft_id)
    if not current: raise LookupError("Inventory movement draft not found")
    if current["status"]=="submitted": raise ValueError("Submitted inventory movements cannot be edited")
    values={**current,**(values or {})}
    with formula_engine._connect() as connection,connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute(sql.SQL('UPDATE {}.{} SET status=\'draft\',movement_date=%s,movement_type=%s,product=%s,from_store=%s,to_store=%s,quantity=%s,note=%s,'
            'updated_at=now(),version=version+1 WHERE id=%s AND version=%s AND is_deleted=false AND status<>\'submitted\' RETURNING *').format(
            sql.Identifier(config.TRANSACTION_SCHEMA),sql.Identifier(DRAFT_TABLE)),(values.get("date") or values.get("movement_date"),_text(values.get("type") or values.get("movement_type")),
            _text(values.get("product")),_text(values.get("from_store")),_text(values.get("to_store")),int(values.get("quantity") or 0),_text(values.get("note")),int(draft_id),int(expected_version)))
        row=cursor.fetchone()
        if not row: raise RuntimeError("Draft changed concurrently; refresh and retry")
        connection.commit();return _draft_payload(row)


def set_draft_state(draft_id,state):
    if state not in {"validated","previewed"}: raise ValueError("Invalid draft state")
    with formula_engine._connect() as connection:
        draft=get_draft(draft_id,connection,True)
        if not draft: raise LookupError("Inventory movement draft not found")
        movement=validate_movement({"date":draft["movement_date"],"type":draft["movement_type"],"product":draft["product"],"from_store":draft["from_store"],"to_store":draft["to_store"],"quantity":draft["quantity"],"note":draft["note"]},check_stock=False)
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(sql.SQL('UPDATE {}.{} SET status=%s,updated_at=now(),version=version+1 WHERE id=%s RETURNING *').format(sql.Identifier(config.TRANSACTION_SCHEMA),sql.Identifier(DRAFT_TABLE)),(state,int(draft_id)));row=cursor.fetchone()
        connection.commit();return {"draft":_draft_payload(row),"movement":movement}


def submit_draft(draft_id,submission_key,submitted_by,connection=None,commit=True):
    owns=connection is None;connection=connection or formula_engine._connect()
    if owns: connection.set_session(isolation_level="SERIALIZABLE",autocommit=False)
    try:
        draft=get_draft(draft_id,connection,True)
        if not draft: raise LookupError("Inventory movement draft not found")
        if str(draft["submission_key"])!=_text(submission_key): raise ValueError("Invalid submission identity")
        if draft["status"]=="submitted":
            if commit: connection.commit()
            return {"draft":draft,"movement_id":draft["submitted_movement_id"],"idempotent":True}
        if draft["status"]!="previewed": raise InventoryValidationError(["movement must be previewed before submit"])
        values={"date":draft["movement_date"],"type":draft["movement_type"],"product":draft["product"],"from_store":draft["from_store"],"to_store":draft["to_store"],"quantity":draft["quantity"],"note":draft["note"],"submission_key":str(draft["submission_key"]),"confirmed":True}
        result=submit_movement(values,connection=connection,commit=False)
        with connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(sql.SQL('UPDATE {}.{} SET status=\'submitted\',submitted_movement_id=%s,submitted_json=%s::jsonb,submitted_at=now(),updated_at=now(),version=version+1 WHERE id=%s RETURNING *').format(
                sql.Identifier(config.TRANSACTION_SCHEMA),sql.Identifier(DRAFT_TABLE)),(result["movement_id"],json.dumps({**result["movement"],"submitted_by":submitted_by}),int(draft_id)));saved=cursor.fetchone()
        if commit: connection.commit()
        return {"draft":_draft_payload(saved),"movement_id":result["movement_id"],"idempotent":result["idempotent"]}
    except Exception:
        connection.rollback();raise
    finally:
        if owns: connection.close()


def remove_draft(draft_id,removed_by,reason="",connection=None,commit=True):
    return draft_management.remove_draft(DRAFT_TABLE,draft_id,removed_by,reason,connection=connection,commit=commit)


def recent_insertions(filters=None,page=1,page_size=20):
    filters=filters or {};page,page_size,offset=draft_management.paging(page,page_size);params={"limit":page_size,"offset":offset};clauses=["d.status='submitted'","d.is_deleted=false"]
    for key,column in (("date_from",'i."Date">='),("date_to",'i."Date"<='),("type",'i."Type"='),("product",'i."Product"=')):
        if filters.get(key):params[key]=filters[key];clauses.append(f"{column}%({key})s")
    if filters.get("store"):params["store"]=filters["store"];clauses.append("(i.\"From_Store\"=%(store)s OR i.\"To_Store\"=%(store)s)")
    with formula_engine._connect() as connection,connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute(sql.SQL('SELECT d.id draft_id,d.submitted_at,i.id record_id,i."Date" movement_date,i."Type" movement_type,i."Product" product,'
            'i."From_Store" from_store,i."To_Store" to_store,i."Qty" quantity,i."Note" note,COUNT(*) OVER() total_count FROM {}.{} d '
            'JOIN {}."Sotephwar_Inventory" i ON i.id=d.submitted_movement_id WHERE '+" AND ".join(clauses)+' ORDER BY d.submitted_at DESC LIMIT %(limit)s OFFSET %(offset)s').format(
            sql.Identifier(config.TRANSACTION_SCHEMA),sql.Identifier(DRAFT_TABLE),sql.Identifier(config.TRANSACTION_SCHEMA)),params);rows=[dict(x) for x in cursor.fetchall()]
    total=int(rows[0].pop("total_count")) if rows else 0
    for row in rows:row["movement_date"]=row["movement_date"].isoformat();row["submitted_at"]=row["submitted_at"].isoformat() if row["submitted_at"] else None;row["quantity"]=int(row["quantity"] or 0);row["reference"]=f"INV-{row['draft_id']:06d}"
    return {"records":rows,"page":page,"page_size":page_size,"total":total,"pages":max(1,(total+page_size-1)//page_size)}


def submission_details(draft_id):
    with formula_engine._connect() as connection,connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute(sql.SQL("SELECT * FROM {}.{} WHERE id=%s AND status='submitted' AND is_deleted=false").format(sql.Identifier(config.TRANSACTION_SCHEMA),sql.Identifier(DRAFT_TABLE)),(int(draft_id),));row=cursor.fetchone()
    if not row:raise LookupError("Submitted inventory movement not found")
    return _draft_payload(row)


def operational_summary():
    with formula_engine._connect() as connection,connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute(sql.SQL('SELECT COUNT(*) FILTER(WHERE status<>\'submitted\' AND is_deleted=false) open_drafts,COUNT(*) FILTER(WHERE status=\'submitted\' AND submitted_at::date=CURRENT_DATE) movements_today,'
            'COALESCE(SUM(quantity) FILTER(WHERE status=\'submitted\' AND submitted_at::date=CURRENT_DATE AND movement_type IN (\'Production\',\'Transfer\')),0) quantity_in_today,'
            'COALESCE(SUM(quantity) FILTER(WHERE status=\'submitted\' AND submitted_at::date=CURRENT_DATE AND movement_type IN (\'Sale\',\'Transfer\')),0) quantity_out_today FROM {}.{}').format(sql.Identifier(config.TRANSACTION_SCHEMA),sql.Identifier(DRAFT_TABLE)));return dict(cursor.fetchone())
