import os
import sys
from datetime import date
from html import escape
import json

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from flask import Flask, jsonify, request
import psycopg2
import psycopg2.extras

import config
from tools import formula_engine


app = Flask(__name__)
DEFAULT_HOST = os.environ.get("RECEIVE_PAYMENT_HOST", "127.0.0.1")
# Chromium blocks 5060 as an unsafe SIP port, so default to a nearby browser-safe port.
DEFAULT_PORT = int(os.environ.get("RECEIVE_PAYMENT_PORT", "5059"))


@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


def _connect():
    return formula_engine._connect()


def _voucher_query(where_sql="", limit_sql="LIMIT 100", order_sql='ORDER BY "Invoice_Date" DESC NULLS LAST, "Sector", "Invoice_Number"'):
    schema = config.TRANSACTION_SCHEMA.replace('"', '""')
    payment_table = formula_engine._payment_receive_table_ref()
    return f'''
    WITH farm_source AS (
      SELECT
        'Farm' AS "Sector",
        f."Invoice_Number"::text AS "Invoice_Number",
        COALESCE(NULLIF(TRIM(f."Customer"), ''), '') AS "Customer",
        '' AS "Sote_Type",
        f."Date" AS "Invoice_Date",
        COALESCE(SUM(f."Total_Amount"), 0) AS "Voucher_Total",
        COALESCE(SUM(f."Total_Received"), 0) AS "Source_Total_Received",
        COALESCE(SUM(f."Outstanding_Balance"), 0) AS "Source_Outstanding_Balance",
        COALESCE(MAX(f."Payment_Status"), '') AS "Source_Payment_Status",
        COALESCE(STRING_AGG(DISTINCT NULLIF(TRIM(f."Note"), ''), ' | ' ORDER BY NULLIF(TRIM(f."Note"), '')), '') AS "Note"
      FROM "{schema}"."farm_transection" f
      WHERE COALESCE(f.__nc_deleted, false) = false
        AND f."Invoice_Number" IS NOT NULL
      GROUP BY f."Invoice_Number"::text, f."Date", COALESCE(NULLIF(TRIM(f."Customer"), ''), '')
    ),
    sote_source AS (
      SELECT
        'Sote Phwar' AS "Sector",
        s."Invoice_Number"::text AS "Invoice_Number",
        COALESCE(NULLIF(TRIM(s."Customer_Name"), ''), '') AS "Customer",
        COALESCE(STRING_AGG(DISTINCT NULLIF(TRIM(s."Item"), ''), ', ' ORDER BY NULLIF(TRIM(s."Item"), '')), '') AS "Sote_Type",
        s."Invoice_Date" AS "Invoice_Date",
        COALESCE(SUM(s."Total_Amount"), 0) AS "Voucher_Total",
        COALESCE(SUM(s."Total_Received"), 0) AS "Source_Total_Received",
        COALESCE(SUM(s."Outstanding_Balance"), 0) AS "Source_Outstanding_Balance",
        COALESCE(MAX(s."Payment_Status"), '') AS "Source_Payment_Status",
        COALESCE(STRING_AGG(DISTINCT NULLIF(TRIM(s."Note"), ''), ' | ' ORDER BY NULLIF(TRIM(s."Note"), '')), '') AS "Note"
      FROM "{schema}"."Sotephwar_Transection" s
      WHERE COALESCE(s.__nc_deleted, false) = false
        AND s."Invoice_Number" IS NOT NULL
      GROUP BY s."Invoice_Number"::text, s."Invoice_Date", COALESCE(NULLIF(TRIM(s."Customer_Name"), ''), '')
    ),
    source_vouchers AS (
      SELECT * FROM farm_source
      UNION ALL
      SELECT * FROM sote_source
    ),
    payments AS (
      SELECT
        "Sector",
        "Voucher_Number"::text AS "Invoice_Number",
        "Invoice_Date",
        COALESCE("Customer", '') AS "Customer",
        COALESCE(SUM("Receive_Amount"), 0) AS "Total_Received"
      FROM {payment_table}
      GROUP BY "Sector", "Voucher_Number"::text, "Invoice_Date", COALESCE("Customer", '')
    ),
    voucher_groups AS (
      SELECT
        sv."Sector",
        sv."Invoice_Number",
        sv."Customer",
        sv."Sote_Type",
        sv."Invoice_Date",
        sv."Voucher_Total",
        GREATEST(sv."Source_Total_Received", COALESCE(p."Total_Received", 0)) AS "Total_Received",
        GREATEST(
          sv."Voucher_Total" - GREATEST(sv."Source_Total_Received", COALESCE(p."Total_Received", 0)),
          0
        ) AS "Outstanding_Balance",
        CASE
          WHEN sv."Voucher_Total" > 0
               AND GREATEST(sv."Source_Total_Received", COALESCE(p."Total_Received", 0)) >= sv."Voucher_Total"
            THEN 'Paid'
          WHEN GREATEST(sv."Source_Total_Received", COALESCE(p."Total_Received", 0)) > 0 THEN 'Partial'
          ELSE 'Outstanding'
        END AS "Payment_Status",
        COALESCE(sv."Note", '') AS "Note"
      FROM source_vouchers sv
      LEFT JOIN payments p
        ON p."Sector" = sv."Sector"
       AND p."Invoice_Number" = sv."Invoice_Number"
       AND COALESCE(p."Customer", '') = COALESCE(sv."Customer", '')
       AND (p."Invoice_Date" = sv."Invoice_Date" OR p."Invoice_Date" IS NULL)
    )
    SELECT
      vg."Sector",
      vg."Invoice_Number",
      COALESCE(vg."Customer", '') AS "Customer",
      COALESCE(vg."Sote_Type", '') AS "Sote_Type",
      vg."Invoice_Date",
      vg."Voucher_Total",
      0 AS "Legacy_Received",
      vg."Total_Received" AS "New_Received",
      vg."Total_Received",
      vg."Outstanding_Balance",
      vg."Payment_Status",
      COALESCE(vg."Note", '') AS "Note"
    FROM voucher_groups vg
    {where_sql}
    {order_sql}
    {limit_sql}
    '''


def _sotephwar_listing_query(where_sql="", limit_sql="LIMIT 100", order_sql='ORDER BY s."Invoice_Date" DESC NULLS LAST, s."Invoice_Number" DESC, s.id DESC'):
    schema = config.TRANSACTION_SCHEMA.replace('"', '""')
    return f'''
    SELECT
      'Sote Phwar' AS "Sector",
      s."Invoice_Number"::text AS "Invoice_Number",
      COALESCE(NULLIF(TRIM(s."Customer_Name"), ''), '') AS "Customer",
      COALESCE(NULLIF(TRIM(s."Item"), ''), '') AS "Sote_Type",
      s."Invoice_Date" AS "Invoice_Date",
      COALESCE(s."Total_Amount", 0) AS "Voucher_Total",
      0 AS "Legacy_Received",
      COALESCE(s."Total_Received", 0) AS "New_Received",
      COALESCE(s."Total_Received", 0) AS "Total_Received",
      COALESCE(s."Outstanding_Balance", 0) AS "Outstanding_Balance",
      COALESCE(s."Payment_Status", '') AS "Payment_Status",
      COALESCE(s."Note", '') AS "Note"
    FROM "{schema}"."Sotephwar_Transection" s
    WHERE COALESCE(s.__nc_deleted, false) = false
      AND s."Invoice_Number" IS NOT NULL
      AND s."Customer_Name" IS NOT NULL
    {where_sql}
    {order_sql}
    {limit_sql}
    '''


def _money_value(value):
    return int(value or 0)


def _voucher_payload(row):
    sector = row["Sector"]
    customer = row.get("Customer") or row.get("Customer_Name") or ""
    sote_type = row.get("Sote_Type") or row.get("Item") or ""
    voucher_total = row.get("Voucher_Total")
    total_received = row.get("Total_Received")
    outstanding_balance = row.get("Outstanding_Balance")
    payment_status = row.get("Payment_Status") or ""
    note = row.get("Note") or ""
    if sector == "Sote Phwar" and "Customer_Name" in row:
        return {
            "sector": sector,
            "invoice_number": row["Invoice_Number"],
            "customer": customer,
            "sote_type": sote_type,
            "invoice_date": row["Invoice_Date"].isoformat() if row["Invoice_Date"] else "",
            "voucher_total": _money_value(voucher_total),
            "legacy_received": 0,
            "new_received": _money_value(total_received),
            "total_received": _money_value(total_received),
            "outstanding_balance": _money_value(outstanding_balance),
            "payment_status": payment_status,
            "note": note,
        }
    return {
        "sector": sector,
        "invoice_number": row["Invoice_Number"],
        "customer": customer,
        "sote_type": sote_type,
        "invoice_date": row["Invoice_Date"].isoformat() if row["Invoice_Date"] else "",
        "voucher_total": _money_value(voucher_total),
        "legacy_received": _money_value(row.get("Legacy_Received")),
        "new_received": _money_value(row.get("New_Received")),
        "total_received": _money_value(total_received),
        "outstanding_balance": _money_value(outstanding_balance),
        "payment_status": payment_status,
        "note": note,
    }


def _fetch_voucher(sector, invoice_number, invoice_date="", customer=""):
    formula_engine.ensure_payment_receive_table()
    conditions = ['vg."Sector" = %(sector)s', 'vg."Invoice_Number" = %(invoice_number)s']
    params = {"sector": sector, "invoice_number": invoice_number}
    if invoice_date:
        conditions.append('vg."Invoice_Date" = %(invoice_date)s')
        params["invoice_date"] = invoice_date
    if customer:
        conditions.append('COALESCE(vg."Customer", \'\') = %(customer)s')
        params["customer"] = customer
    with _connect() as conn:
        conn.set_session(readonly=True)
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                _voucher_query(
                    where_sql="WHERE " + " AND ".join(conditions),
                    limit_sql="LIMIT 1",
                    order_sql="",
                ),
                params,
            )
            row = cur.fetchone()
            conn.rollback()
    return _voucher_payload(row) if row else None


def _normalize_sector_filter(value):
    if value == "Farm":
        return "Farm"
    if value in {"Sote Phwar", "Sotephwar"}:
        return "Sote Phwar"
    return ""


def _list_vouchers(search="", sector="", voucher_number="", invoice_date="", customer=""):
    formula_engine.ensure_payment_receive_table()
    params = {}
    sector = _normalize_sector_filter(sector)
    if sector == "Sote Phwar":
        conditions = ['COALESCE(s."Outstanding_Balance", 0) > 0']
        if search:
            conditions.append('''
            (s."Invoice_Number"::text ILIKE %(search)s
               OR COALESCE(NULLIF(TRIM(s."Customer_Name"), ''), '') ILIKE %(search)s
               OR COALESCE(NULLIF(TRIM(s."Item"), ''), '') ILIKE %(search)s)
            ''')
            params["search"] = f"%{search}%"
        if voucher_number:
            conditions.append('s."Invoice_Number"::text = %(voucher_number)s')
            params["voucher_number"] = voucher_number
        if invoice_date:
            conditions.append('s."Invoice_Date" = %(invoice_date)s')
            params["invoice_date"] = invoice_date
        if customer:
            conditions.append('COALESCE(NULLIF(TRIM(s."Customer_Name"), \'\'), \'\') ILIKE %(customer)s')
            params["customer"] = f"%{customer}%"
        where_sql = " AND " + " AND ".join(conditions)
        with _connect() as conn:
            conn.set_session(readonly=True)
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(_sotephwar_listing_query(where_sql=where_sql), params)
                rows = cur.fetchall()
                conn.rollback()
        return [_voucher_payload(row) for row in rows]

    conditions = []
    if sector:
        conditions.append('vg."Sector" = %(sector)s')
        params["sector"] = sector
    if search:
        conditions.append('''
        (vg."Sector" ILIKE %(search)s
           OR vg."Invoice_Number" ILIKE %(search)s
           OR COALESCE(vg."Customer", '') ILIKE %(search)s
           OR COALESCE(vg."Sote_Type", '') ILIKE %(search)s)
        ''')
        params["search"] = f"%{search}%"
    if voucher_number:
        conditions.append('vg."Invoice_Number" = %(voucher_number)s')
        params["voucher_number"] = voucher_number
    if invoice_date:
        conditions.append('vg."Invoice_Date" = %(invoice_date)s')
        params["invoice_date"] = invoice_date
    if customer:
        conditions.append('COALESCE(vg."Customer", \'\') ILIKE %(customer)s')
        params["customer"] = f"%{customer}%"
    conditions.append('''
    (
      COALESCE(vg."Outstanding_Balance", 0) > 0
      OR COALESCE(vg."Payment_Status", '') IN ('Outstanding', 'Partial')
    )
    ''')
    where_sql = "WHERE " + " AND ".join(conditions)

    with _connect() as conn:
        conn.set_session(readonly=True)
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(_voucher_query(where_sql=where_sql), params)
            rows = cur.fetchall()
            conn.rollback()
    return [_voucher_payload(row) for row in rows]


def _customer_suggestions(sector=""):
    sector = _normalize_sector_filter(sector)
    schema = config.TRANSACTION_SCHEMA.replace('"', '""')
    queries = []
    if sector in {"", "Farm"}:
        queries.append(f'''
            SELECT DISTINCT NULLIF(TRIM("Customer"), '') AS customer
            FROM "{schema}"."farm_transection"
            WHERE COALESCE(__nc_deleted, false) = false
              AND NULLIF(TRIM("Customer"), '') IS NOT NULL
        ''')
    if sector in {"", "Sote Phwar"}:
        queries.append(f'''
            SELECT DISTINCT NULLIF(TRIM("Customer_Name"), '') AS customer
            FROM "{schema}"."Sotephwar_Transection"
            WHERE COALESCE(__nc_deleted, false) = false
              AND NULLIF(TRIM("Customer_Name"), '') IS NOT NULL
        ''')
    if not queries:
        return []

    with _connect() as conn:
        conn.set_session(readonly=True)
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                f'''
                SELECT customer
                FROM ({" UNION ".join(queries)}) customers
                ORDER BY customer
                LIMIT 300
                '''
            )
            rows = cur.fetchall()
            conn.rollback()
    return [row["customer"] for row in rows if row.get("customer")]


def _server_render_rows(vouchers):
    rows = []
    for voucher in vouchers:
        rows.append(
            "<tr>"
            f"<td>{escape(voucher['sector'])}</td>"
            f"<td>{escape(voucher['invoice_number'])}</td>"
            f"<td>{escape(voucher['customer'])}</td>"
            f"<td>{escape(voucher['sote_type'])}</td>"
            f"<td>{escape(voucher['invoice_date'])}</td>"
            f"<td>{voucher['voucher_total']:,}</td>"
            f"<td>{voucher['total_received']:,}</td>"
            f"<td>{voucher['outstanding_balance']:,}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def _sector_option(value, label, sector_filter):
    selected = " selected" if value == sector_filter else ""
    return f'<option value="{escape(value)}"{selected}>{escape(label)}</option>'


def _basic_payment_page(
    message="",
    error=False,
    sector_filter="Farm",
    voucher_number_filter="",
    invoice_date_filter="",
    customer_filter="",
):
    sector_filter = _normalize_sector_filter(sector_filter) or ""
    voucher_number_filter = (voucher_number_filter or "").strip()
    invoice_date_filter = (invoice_date_filter or "").strip()
    customer_filter = (customer_filter or "").strip()
    try:
        vouchers = _list_vouchers(
            sector=sector_filter,
            voucher_number=voucher_number_filter,
            invoice_date=invoice_date_filter,
            customer=customer_filter,
        )
    except Exception as exc:
        vouchers = []
        message = f"Could not load vouchers: {exc}"
        error = True

    try:
        customer_options = "\n".join(
            f'<option value="{escape(customer)}"></option>'
            for customer in _customer_suggestions(sector_filter)
        )
    except Exception:
        customer_options = ""

    rows = []
    for voucher in vouchers:
        key = f"{voucher['sector']}||{voucher['invoice_number']}||{voucher['invoice_date']}||{voucher['customer']}"
        summary = (
            f"{voucher['sector']} / {voucher['invoice_number']} / "
            f"{voucher['customer'] or '-'} / Outstanding {voucher['outstanding_balance']:,}"
        )
        rows.append(
            f"<tr class=\"voucher-row\" data-voucher-summary=\"{escape(summary)}\" tabindex=\"0\">"
            f"<td><input type=\"radio\" name=\"voucher_key\" value=\"{escape(key)}\" aria-label=\"Select voucher {escape(summary)}\" required></td>"
            f"<td>{escape(voucher['sector'])}</td>"
            f"<td>{escape(voucher['invoice_number'])}</td>"
            f"<td>{escape(voucher['customer'])}</td>"
            f"<td>{escape(voucher['sote_type'])}</td>"
            f"<td>{escape(voucher['invoice_date'])}</td>"
            f"<td>{voucher['voucher_total']:,}</td>"
            f"<td>{voucher['total_received']:,}</td>"
            f"<td>{voucher['outstanding_balance']:,}</td>"
            f"<td>{escape(voucher.get('note', ''))}</td>"
            "</tr>"
        )
    if not rows:
        rows.append(
            '<tr><td colspan="10" class="empty">'
            "No vouchers are available. Check the database connection, then refresh this page."
            "</td></tr>"
        )
    status_html = ""
    if message:
        status_class = "error" if error else "ok"
        status_html = f'<p class="{status_class}">{escape(message)}</p>'
    return f'''
    <!doctype html>
    <html>
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Receive Payment Basic</title>
        <style>
          body {{ margin: 0; font-family: Arial, sans-serif; background: #f6f7f9; color: #111; }}
          header {{ padding: 18px 22px; background: #fff; border-bottom: 1px solid #ccc; }}
          main {{ padding: 16px; }}
          form {{ display: grid; grid-template-columns: 1fr 360px; gap: 16px; }}
          .filters {{ display: flex; align-items: end; gap: 10px; padding: 12px 14px; border-bottom: 1px solid #ddd; }}
          .filters form {{ display: grid; grid-template-columns: 150px 160px 170px minmax(220px, 1fr) auto; gap: 10px; align-items: end; width: 100%; }}
          section {{ background: #fff; border: 1px solid #ccc; border-radius: 6px; overflow: hidden; }}
          .side {{ padding: 14px; }}
          .table-wrap {{ max-height: calc(100vh - 120px); overflow: auto; }}
          table {{ width: 100%; min-width: 980px; border-collapse: collapse; table-layout: auto; }}
          th, td {{ padding: 8px; border-bottom: 1px solid #ddd; text-align: left; font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
          th {{ background: #f1f3f5; }}
          .voucher-row {{ cursor: pointer; }}
          .voucher-row:hover {{ background: #f1faf7; }}
          .voucher-row.selected {{ background: #dff3ee; outline: 2px solid #176b5d; outline-offset: -2px; }}
          input, textarea, button, select {{ width: 100%; box-sizing: border-box; font: inherit; padding: 8px; border-radius: 4px; border: 1px solid #bbb; }}
          input[readonly] {{ background: #f8fafc; color: #374151; }}
          button {{ margin-top: 10px; background: #176b5d; color: white; border: 0; cursor: pointer; font-weight: bold; }}
          .filters button {{ width: auto; min-width: 92px; margin-top: 0; }}
          label {{ display: block; margin: 10px 0 4px; font-size: 12px; font-weight: bold; color: #555; }}
          .ok {{ color: #176b5d; font-weight: bold; }}
          .error {{ color: #b00020; font-weight: bold; }}
          .empty {{ color: #6b7280; white-space: normal; padding: 18px; }}
          @media (max-width: 900px) {{
            form {{ grid-template-columns: 1fr; }}
            .filters form {{ grid-template-columns: 1fr 1fr; }}
            .filters button {{ width: 100%; }}
          }}
        </style>
      </head>
      <body>
        <header><h1>Receive Payment Basic</h1></header>
        <main>
          {status_html}
          <section class="filters">
            <form method="get" action="/receive-payment-basic">
              <div>
                <label>Sector</label>
                <select name="sector">
                  {_sector_option("Farm", "Farm", sector_filter)}
                  {_sector_option("Sote Phwar", "Sote Phwar", sector_filter)}
                  {_sector_option("", "All sectors", sector_filter)}
                </select>
              </div>
              <div>
                <label>Voucher Number</label>
                <input name="voucher_number" value="{escape(voucher_number_filter)}" inputmode="numeric" placeholder="Type voucher no.">
              </div>
              <div>
                <label>Date</label>
                <input name="invoice_date" value="{escape(invoice_date_filter)}" type="date">
              </div>
              <div>
                <label>Customer Name</label>
                <input name="customer" value="{escape(customer_filter)}" list="customerSuggestions" autocomplete="off" placeholder="Type customer name">
                <datalist id="customerSuggestions">
                  {customer_options}
                </datalist>
              </div>
              <button type="submit">View</button>
            </form>
          </section>
          <form method="post" action="/receive-payment-basic">
            <input type="hidden" name="sector_filter" value="{escape(sector_filter)}">
            <input type="hidden" name="voucher_number_filter" value="{escape(voucher_number_filter)}">
            <input type="hidden" name="invoice_date_filter" value="{escape(invoice_date_filter)}">
            <input type="hidden" name="customer_filter" value="{escape(customer_filter)}">
            <section>
              <div class="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th style="width:42px;">Pick</th>
                      <th>Sector</th>
                      <th>Invoice Number</th>
                      <th>Customer</th>
                      <th>Sote Type / Item</th>
                      <th>Invoice Date</th>
                      <th>Voucher Total</th>
                      <th>Total Received</th>
                      <th>Outstanding</th>
                      <th>Note</th>
                    </tr>
                  </thead>
                  <tbody>{"".join(rows)}</tbody>
                </table>
              </div>
            </section>
            <section class="side">
              <label>Selected Voucher</label>
              <input id="selectedVoucher" value="Click a voucher row on the left" readonly>
              <label>Receive Amount</label>
              <input name="receive_amount" inputmode="numeric" placeholder="Enter new receive amount only" required>
              <label>Payment Method</label>
              <input name="payment_method" placeholder="Cash, KPay, Bank...">
              <label>Reference Number</label>
              <input name="reference_number">
              <label>Note</label>
              <textarea id="paymentNote" name="notes" rows="5"></textarea>
              <button type="submit">Save Payment</button>
            </section>
          </form>
        </main>
        <script>
          const rows = Array.from(document.querySelectorAll('.voucher-row'));
          const selectedVoucher = document.getElementById('selectedVoucher');
          const paymentNote = document.getElementById('paymentNote');
          const receiveAmount = document.querySelector('input[name="receive_amount"]');

          function selectRow(row) {{
            rows.forEach(item => item.classList.remove('selected'));
            row.classList.add('selected');
            const radio = row.querySelector('input[type="radio"]');
            radio.checked = true;
            selectedVoucher.value = row.dataset.voucherSummary || radio.value;
            paymentNote.value = row.cells[9] ? row.cells[9].textContent : '';
            receiveAmount.focus();
          }}

          rows.forEach(row => {{
            row.addEventListener('click', () => selectRow(row));
            row.addEventListener('keydown', event => {{
              if (event.key === 'Enter' || event.key === ' ') {{
                event.preventDefault();
                selectRow(row);
              }}
            }});
            row.querySelector('input[type="radio"]').addEventListener('change', () => selectRow(row));
          }});
        </script>
      </body>
    </html>
    ''', 200, {"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"}


@app.get("/")
@app.get("/receive-payment")
def receive_payment_page():
    vouchers = _list_vouchers()
    return (
        PAGE_HTML
        .replace("__INITIAL_ROWS__", _server_render_rows(vouchers))
        .replace("__INITIAL_VOUCHERS__", json.dumps(vouchers))
    )


@app.get("/health")
def health():
    return jsonify({"ok": True})


@app.get("/debug")
def debug_page():
    return '''
    <!doctype html>
    <html>
      <head><title>Receive Payment Debug</title></head>
      <body style="font-family: Arial, sans-serif; padding: 32px;">
        <h1>Receive Payment Debug</h1>
        <p>If you can see this page, the localhost server is reachable.</p>
        <p><a href="/receive-payment">Open Receive Payment</a></p>
      </body>
    </html>
    ''', 200, {"Cache-Control": "no-store, max-age=0"}


@app.get("/visible")
def visible_page():
    return '''
    <!doctype html>
    <html>
      <head>
        <title>VISIBLE TEST</title>
      </head>
      <body style="margin:0; background:#ffffff; color:#000000; font-family:Arial,sans-serif;">
        <div style="border:12px solid red; padding:40px; margin:30px;">
          <h1 style="font-size:48px; color:#000000;">VISIBLE TEST PAGE</h1>
          <p style="font-size:24px;">If you can see this, the browser can render localhost HTML.</p>
          <p style="font-size:20px;"><a href="/plain">Open plain voucher table</a></p>
          <p style="font-size:20px;"><a href="/receive-payment">Open Receive Payment app</a></p>
        </div>
      </body>
    </html>
    ''', 200, {"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"}


@app.get("/plain")
def plain_page():
    vouchers = _list_vouchers()
    rows = "\n".join(
        "<tr>"
        f"<td>{escape(v['sector'])}</td>"
        f"<td>{escape(v['invoice_number'])}</td>"
        f"<td>{escape(v['customer'])}</td>"
        f"<td>{escape(v['sote_type'])}</td>"
        f"<td>{escape(v['invoice_date'])}</td>"
        f"<td>{v['voucher_total']:,}</td>"
        f"<td>{v['total_received']:,}</td>"
        f"<td>{v['outstanding_balance']:,}</td>"
        "</tr>"
        for v in vouchers
    )
    return f'''
    <!doctype html>
    <html>
      <head>
        <title>Receive Payment Plain</title>
        <style>
          body {{ font-family: Arial, sans-serif; padding: 24px; }}
          table {{ border-collapse: collapse; width: 100%; }}
          th, td {{ border: 1px solid #999; padding: 6px 8px; text-align: left; }}
          th {{ background: #eee; }}
        </style>
      </head>
      <body>
        <h1>Receive Payment Plain</h1>
        <p>If this page is visible, the browser can display localhost content.</p>
        <p><a href="/receive-payment">Open full Receive Payment page</a></p>
        <table>
          <thead>
            <tr>
              <th>Sector</th>
              <th>Invoice Number</th>
              <th>Customer</th>
              <th>Sote Type / Item</th>
              <th>Invoice Date</th>
              <th>Voucher Total</th>
              <th>Total Received</th>
              <th>Outstanding Balance</th>
            </tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>
      </body>
    </html>
    ''', 200, {"Cache-Control": "no-store, max-age=0"}


@app.route("/receive-payment-basic", methods=["GET", "POST"])
def receive_payment_basic_page():
    sector_filter = _normalize_sector_filter(
        request.values.get("sector") or request.values.get("sector_filter") or "Farm"
    )
    voucher_number_filter = (
        request.values.get("voucher_number") or request.values.get("voucher_number_filter") or ""
    ).strip()
    invoice_date_filter = (
        request.values.get("invoice_date") or request.values.get("invoice_date_filter") or ""
    ).strip()
    customer_filter = (
        request.values.get("customer") or request.values.get("customer_filter") or ""
    ).strip()
    filter_values = {
        "sector_filter": sector_filter,
        "voucher_number_filter": voucher_number_filter,
        "invoice_date_filter": invoice_date_filter,
        "customer_filter": customer_filter,
    }
    if request.method == "GET":
        return _basic_payment_page(**filter_values)

    voucher_key = request.form.get("voucher_key") or ""
    key_parts = voucher_key.split("||")
    if len(key_parts) < 2:
        return _basic_payment_page("Select a voucher before saving.", error=True, **filter_values)
    sector, invoice_number = key_parts[:2]
    selected_invoice_date = key_parts[2] if len(key_parts) > 2 else ""
    selected_customer = key_parts[3] if len(key_parts) > 3 else ""
    payment_method = (request.form.get("payment_method") or "").strip()
    reference_number = (request.form.get("reference_number") or "").strip()
    notes = (request.form.get("notes") or "").strip()
    try:
        receive_amount = int((request.form.get("receive_amount") or "0").replace(",", ""))
    except ValueError:
        receive_amount = 0

    if receive_amount <= 0:
        return _basic_payment_page("Receive Amount must be greater than zero.", error=True, **filter_values)

    voucher = _fetch_voucher(sector, invoice_number, selected_invoice_date, selected_customer)
    if not voucher:
        return _basic_payment_page("Voucher not found.", error=True, **filter_values)

    try:
        _insert_payment_receive(
            sector=sector,
            voucher_number=invoice_number,
            invoice_date=voucher["invoice_date"],
            customer=voucher["customer"],
            receive_amount=receive_amount,
            payment_method=payment_method,
            reference_number=reference_number,
            notes=notes,
            recorded_by="Receive Payment Basic Page",
        )
    except LookupError:
        return _basic_payment_page("Voucher not found.", error=True, **filter_values)
    except ValueError as exc:
        return _basic_payment_page(str(exc), error=True, **filter_values)
    return _basic_payment_page("Payment saved. Totals refreshed.", **filter_values)


@app.get("/api/vouchers")
def list_vouchers():
    search = (request.args.get("q") or "").strip()
    sector = (request.args.get("sector") or "").strip()
    voucher_number = (request.args.get("voucher_number") or "").strip()
    invoice_date = (request.args.get("invoice_date") or "").strip()
    customer = (request.args.get("customer") or "").strip()
    return jsonify({
        "ok": True,
        "vouchers": _list_vouchers(search, sector, voucher_number, invoice_date, customer),
    })


@app.get("/api/voucher")
def get_voucher():
    sector = (request.args.get("sector") or "").strip()
    invoice_number = (request.args.get("invoice_number") or "").strip()
    invoice_date = (request.args.get("invoice_date") or "").strip()
    customer = (request.args.get("customer") or "").strip()
    if not sector or not invoice_number:
        return jsonify({"ok": False, "error": "sector and invoice_number are required"}), 400
    voucher = _fetch_voucher(sector, invoice_number, invoice_date, customer)
    if not voucher:
        return jsonify({"ok": False, "error": "Voucher not found"}), 404
    return jsonify({"ok": True, "voucher": voucher})


@app.post("/api/payment-receive")
def create_payment_receive():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"ok": False, "error": "JSON body is required"}), 400

    sector = str(payload.get("sector") or "").strip()
    invoice_number = str(payload.get("invoice_number") or "").strip()
    invoice_date = str(payload.get("invoice_date") or "").strip()
    customer = str(payload.get("customer") or "").strip()
    payment_method = str(payload.get("payment_method") or "").strip()
    reference_number = str(payload.get("reference_number") or "").strip()
    notes = str(payload.get("notes") or "").strip()
    recorded_by = str(payload.get("recorded_by") or "Receive Payment Page").strip()
    try:
        receive_amount = int(str(payload.get("receive_amount") or "0").replace(",", ""))
    except ValueError:
        receive_amount = 0

    if sector not in {"Farm", "Sote Phwar"}:
        return jsonify({"ok": False, "error": "sector must be Farm or Sote Phwar"}), 400
    if not invoice_number:
        return jsonify({"ok": False, "error": "invoice_number is required"}), 400
    if receive_amount <= 0:
        return jsonify({"ok": False, "error": "receive_amount must be greater than zero"}), 400

    voucher = _fetch_voucher(sector, invoice_number, invoice_date, customer)
    if not voucher:
        return jsonify({"ok": False, "error": "Voucher not found"}), 404

    try:
        row = _insert_payment_receive(
            sector=sector,
            voucher_number=invoice_number,
            invoice_date=voucher["invoice_date"],
            customer=voucher["customer"],
            receive_amount=receive_amount,
            payment_method=payment_method,
            reference_number=reference_number,
            notes=notes,
            recorded_by=recorded_by,
        )
    except LookupError:
        return jsonify({"ok": False, "error": "Voucher not found"}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400

    refreshed = _fetch_voucher(sector, invoice_number, voucher["invoice_date"], voucher["customer"])
    return jsonify({"ok": True, "payment": row, "voucher": refreshed})


@app.route("/api/payment-receive", methods=["OPTIONS"])
@app.route("/api/vouchers", methods=["OPTIONS"])
@app.route("/api/voucher", methods=["OPTIONS"])
def api_options():
    return "", 204


def _payment_total_received(sector, voucher_number):
    formula_engine.ensure_payment_receive_table()
    with _connect() as conn:
        conn.set_session(readonly=True)
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                f'''
                SELECT COALESCE(SUM("Receive_Amount"), 0) AS total_received
                FROM {formula_engine._payment_receive_table_ref()}
                WHERE "Sector" = %(sector)s
                  AND "Voucher_Number" = %(voucher_number)s
                ''',
                {"sector": sector, "voucher_number": voucher_number},
            )
            row = cur.fetchone()
            conn.rollback()
    return _money_value(row["total_received"] if row else 0)


def _insert_payment_receive(**values):
    saved = formula_engine.save_payment_receive(
        sector=values["sector"],
        voucher_number=values["voucher_number"],
        receive_amount=values["receive_amount"],
        payment_method=values.get("payment_method") or "",
        reference_number=values.get("reference_number") or "",
        notes=values.get("notes") or "",
        recorded_by=values.get("recorded_by") or "",
        invoice_date=values.get("invoice_date") or None,
        customer=values.get("customer") or None,
    )
    row = dict(saved["payment"])
    for key in ("invoice_amount", "previous_paid", "receive_amount", "outstanding_balance"):
        row[key] = _money_value(row.get(key))
    if row.get("receive_date") and hasattr(row["receive_date"], "isoformat"):
        row["receive_date"] = row["receive_date"].isoformat()
    if row.get("invoice_date") and hasattr(row["invoice_date"], "isoformat"):
        row["invoice_date"] = row["invoice_date"].isoformat()
    return row


PAGE_HTML = r'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Receive Payment</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --text: #17202a;
      --muted: #6b7280;
      --line: #d8dde5;
      --accent: #1f7a6b;
      --accent-dark: #165d52;
      --danger: #a33a3a;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--text);
    }
    header {
      height: 64px;
      display: flex;
      align-items: center;
      padding: 0 24px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }
    h1 { margin: 0; font-size: 21px; font-weight: 650; }
    main {
      display: grid;
      grid-template-columns: minmax(460px, 1.35fr) minmax(360px, .85fr);
      gap: 18px;
      padding: 18px;
      max-width: 1440px;
      margin: 0 auto;
    }
    section {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      min-width: 0;
    }
    .toolbar {
      padding: 14px;
      border-bottom: 1px solid var(--line);
      display: flex;
      gap: 10px;
      align-items: center;
    }
    input, select, textarea, button {
      font: inherit;
      border-radius: 6px;
    }
    input, select, textarea {
      width: 100%;
      border: 1px solid var(--line);
      padding: 9px 10px;
      background: #fff;
      color: var(--text);
    }
    input[readonly] { background: #f8fafc; color: #374151; }
    textarea { min-height: 82px; resize: vertical; }
    button {
      border: 0;
      padding: 10px 14px;
      background: var(--accent);
      color: #fff;
      cursor: pointer;
      font-weight: 650;
    }
    button:hover { background: var(--accent-dark); }
    button:disabled { opacity: .5; cursor: not-allowed; }
    table {
      width: 100%;
      min-width: 980px;
      border-collapse: collapse;
      table-layout: auto;
    }
    th, td {
      padding: 9px 10px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      font-size: 13px;
    }
    th { color: var(--muted); font-weight: 650; background: #fbfcfd; }
    tr { cursor: pointer; }
    tr.selected { background: #e9f5f2; }
    .table-wrap { max-height: calc(100vh - 146px); overflow: auto; }
    .side { padding: 16px; }
    .grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
    }
    .field { margin-bottom: 12px; }
    label {
      display: block;
      font-size: 12px;
      color: var(--muted);
      margin-bottom: 5px;
      font-weight: 650;
    }
    .form-actions {
      display: flex;
      justify-content: flex-end;
      align-items: center;
      gap: 12px;
      margin-top: 12px;
    }
    .status { color: var(--muted); font-size: 13px; }
    .status.error { color: var(--danger); }
    @media (max-width: 900px) {
      main { grid-template-columns: 1fr; }
      .table-wrap { max-height: 460px; }
    }
  </style>
</head>
<body>
  <header><h1>Receive Payment</h1></header>
  <main>
    <section>
      <div class="toolbar">
        <input id="search" type="search" placeholder="Search sector, invoice number, customer">
        <button id="refresh" type="button">Refresh</button>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Sector</th>
              <th>Invoice Number</th>
              <th>Customer</th>
              <th>Sote Type / Item</th>
              <th>Invoice Date</th>
              <th>Voucher Total</th>
              <th>Total Received</th>
              <th>Outstanding</th>
            </tr>
          </thead>
          <tbody id="voucherRows">__INITIAL_ROWS__</tbody>
        </table>
      </div>
    </section>

    <section class="side">
      <div class="grid">
        <div class="field"><label>Sector</label><input id="sector" readonly></div>
        <div class="field"><label>Invoice Number</label><input id="invoiceNumber" readonly></div>
        <div class="field"><label>Customer</label><input id="customer" readonly></div>
        <div class="field"><label>Sote Type / Item</label><input id="soteType" readonly></div>
        <div class="field"><label>Invoice Date</label><input id="invoiceDate" readonly></div>
        <div class="field"><label>Voucher Total</label><input id="voucherTotal" readonly></div>
        <div class="field"><label>Total Received</label><input id="totalReceived" readonly></div>
      </div>
      <div class="field"><label>Outstanding Balance</label><input id="outstandingBalance" readonly></div>

      <form id="paymentForm">
        <div class="field"><label>Receive Amount</label><input id="receiveAmount" inputmode="numeric" required></div>
        <div class="field"><label>Payment Method</label><input id="paymentMethod" placeholder="Cash, KPay, Bank..."></div>
        <div class="field"><label>Reference Number</label><input id="referenceNumber"></div>
        <div class="field"><label>Notes</label><textarea id="notes"></textarea></div>
        <div class="form-actions">
          <span id="status" class="status">Select a voucher.</span>
          <button id="save" type="submit" disabled>Save Payment</button>
        </div>
      </form>
    </section>
  </main>

  <script>
    const rowsEl = document.getElementById('voucherRows');
    const statusEl = document.getElementById('status');
    const saveEl = document.getElementById('save');
    let vouchers = __INITIAL_VOUCHERS__;
    let selected = null;

    const money = value => Number(value || 0).toLocaleString();
    const setStatus = (text, error=false) => {
      statusEl.textContent = text;
      statusEl.className = error ? 'status error' : 'status';
    };
    const fill = voucher => {
      selected = voucher;
      document.getElementById('sector').value = voucher?.sector || '';
      document.getElementById('invoiceNumber').value = voucher?.invoice_number || '';
      document.getElementById('customer').value = voucher?.customer || '';
      document.getElementById('soteType').value = voucher?.sote_type || '';
      document.getElementById('invoiceDate').value = voucher?.invoice_date || '';
      document.getElementById('voucherTotal').value = voucher ? money(voucher.voucher_total) : '';
      document.getElementById('totalReceived').value = voucher ? money(voucher.total_received) : '';
      document.getElementById('outstandingBalance').value = voucher ? money(voucher.outstanding_balance) : '';
      saveEl.disabled = !voucher;
      setStatus(voucher ? 'Ready.' : 'Select a voucher.');
      render();
    };
    const render = () => {
      rowsEl.innerHTML = '';
      vouchers.forEach(v => {
        const tr = document.createElement('tr');
        if (
          selected &&
          selected.sector === v.sector &&
          selected.invoice_number === v.invoice_number &&
          selected.invoice_date === v.invoice_date &&
          selected.customer === v.customer
        ) tr.className = 'selected';
        tr.innerHTML = `
          <td>${v.sector}</td>
          <td>${v.invoice_number}</td>
          <td>${v.customer || ''}</td>
          <td>${v.sote_type || ''}</td>
          <td>${v.invoice_date || ''}</td>
          <td>${money(v.voucher_total)}</td>
          <td>${money(v.total_received)}</td>
          <td>${money(v.outstanding_balance)}</td>
        `;
        tr.addEventListener('click', () => fill(v));
        rowsEl.appendChild(tr);
      });
    };
    async function loadVouchers() {
      const q = document.getElementById('search').value.trim();
      const response = await fetch('/api/vouchers' + (q ? '?q=' + encodeURIComponent(q) : ''));
      const data = await response.json();
      if (!data.ok) throw new Error(data.error || 'Could not load vouchers');
      vouchers = data.vouchers;
      if (selected) {
        const refreshed = vouchers.find(v =>
          v.sector === selected.sector &&
          v.invoice_number === selected.invoice_number &&
          v.invoice_date === selected.invoice_date &&
          v.customer === selected.customer
        );
        selected = refreshed || null;
        if (selected) fill(selected);
      }
      render();
    }
    async function refreshSelected() {
      if (!selected) return;
      const response = await fetch(
        `/api/voucher?sector=${encodeURIComponent(selected.sector)}` +
        `&invoice_number=${encodeURIComponent(selected.invoice_number)}` +
        `&invoice_date=${encodeURIComponent(selected.invoice_date || '')}` +
        `&customer=${encodeURIComponent(selected.customer || '')}`
      );
      const data = await response.json();
      if (data.ok) fill(data.voucher);
      await loadVouchers();
    }
    document.getElementById('refresh').addEventListener('click', () => loadVouchers().catch(err => setStatus(err.message, true)));
    document.getElementById('search').addEventListener('input', () => loadVouchers().catch(err => setStatus(err.message, true)));
    document.getElementById('paymentForm').addEventListener('submit', async event => {
      event.preventDefault();
      if (!selected) return;
      saveEl.disabled = true;
      setStatus('Saving...');
      try {
        const response = await fetch('/api/payment-receive', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            sector: selected.sector,
            invoice_number: selected.invoice_number,
            invoice_date: selected.invoice_date,
            customer: selected.customer,
            receive_amount: document.getElementById('receiveAmount').value,
            payment_method: document.getElementById('paymentMethod').value,
            reference_number: document.getElementById('referenceNumber').value,
            notes: document.getElementById('notes').value
          })
        });
        const data = await response.json();
        if (!data.ok) throw new Error(data.error || 'Save failed');
        document.getElementById('receiveAmount').value = '';
        document.getElementById('paymentMethod').value = '';
        document.getElementById('referenceNumber').value = '';
        document.getElementById('notes').value = '';
        fill(data.voucher);
        await refreshSelected();
        setStatus('Payment saved. Totals refreshed.');
      } catch (err) {
        setStatus(err.message, true);
      } finally {
        saveEl.disabled = !selected;
      }
    });
    loadVouchers().catch(err => setStatus(err.message, true));
  </script>
</body>
</html>
'''


if __name__ == "__main__":
    from waitress import serve

    serve(app, host=DEFAULT_HOST, port=DEFAULT_PORT, threads=4)
