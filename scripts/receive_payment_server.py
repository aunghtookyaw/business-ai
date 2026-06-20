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


@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


def _connect():
    return psycopg2.connect(
        host=config.POSTGRES_HOST,
        port=config.POSTGRES_PORT,
        database=config.POSTGRES_DB,
        user=config.POSTGRES_USER,
        password=config.POSTGRES_PASSWORD,
    )


def _voucher_query(where_sql="", limit_sql="LIMIT 100", order_sql='ORDER BY "Invoice_Date" DESC NULLS LAST, "Sector", "Invoice_Number"'):
    schema = config.TRANSACTION_SCHEMA.replace('"', '""')
    return f'''
    WITH voucher_groups AS (
      SELECT
        'Farm' AS "Sector",
        f."Invoice_Number"::text AS "Invoice_Number",
        MIN(NULLIF(TRIM(f."Customer"), '')) AS "Customer",
        MIN(f."Date") AS "Invoice_Date",
        COALESCE(SUM(f."Total_Due"), 0) AS "Voucher_Total",
        COALESCE(MAX(f."Total_Received"), 0) AS "Total_Received",
        COALESCE(MAX(f."Outstanding_Balance"), 0) AS "Outstanding_Balance"
      FROM "{schema}"."farm_transection" f
      WHERE COALESCE(f.__nc_deleted, false) = false
        AND f."Invoice_Number" IS NOT NULL
      GROUP BY f."Invoice_Number"::text

      UNION ALL

      SELECT
        'Sote Phwar' AS "Sector",
        s."Invoice_Number"::text AS "Invoice_Number",
        MIN(NULLIF(TRIM(s."Customer_Name"), '')) AS "Customer",
        MIN(s."Invoice_Date") AS "Invoice_Date",
        COALESCE(SUM(s."Total_Amount"), 0) AS "Voucher_Total",
        COALESCE(MAX(s."Total_Received"), 0) AS "Total_Received",
        COALESCE(MAX(s."Outstanding_Balance"), 0) AS "Outstanding_Balance"
      FROM "{schema}"."Sotephwar_Transection" s
      WHERE COALESCE(s.__nc_deleted, false) = false
        AND s."Invoice_Number" IS NOT NULL
      GROUP BY s."Invoice_Number"::text
    )
    SELECT
      "Sector",
      "Invoice_Number",
      COALESCE("Customer", '') AS "Customer",
      "Invoice_Date",
      "Voucher_Total",
      "Total_Received",
      "Outstanding_Balance"
    FROM voucher_groups
    {where_sql}
    {order_sql}
    {limit_sql}
    '''


def _money_value(value):
    return int(value or 0)


def _voucher_payload(row):
    return {
        "sector": row["Sector"],
        "invoice_number": row["Invoice_Number"],
        "customer": row["Customer"] or "",
        "invoice_date": row["Invoice_Date"].isoformat() if row["Invoice_Date"] else "",
        "voucher_total": _money_value(row["Voucher_Total"]),
        "total_received": _money_value(row["Total_Received"]),
        "outstanding_balance": _money_value(row["Outstanding_Balance"]),
    }


def _fetch_voucher(sector, invoice_number):
    with _connect() as conn:
        conn.set_session(readonly=True)
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                _voucher_query(
                    where_sql='WHERE "Sector" = %(sector)s AND "Invoice_Number" = %(invoice_number)s',
                    limit_sql="LIMIT 1",
                    order_sql="",
                ),
                {"sector": sector, "invoice_number": invoice_number},
            )
            row = cur.fetchone()
            conn.rollback()
    return _voucher_payload(row) if row else None


def _list_vouchers(search=""):
    where_sql = ""
    params = {}
    if search:
        where_sql = '''
        WHERE "Sector" ILIKE %(search)s
           OR "Invoice_Number" ILIKE %(search)s
           OR COALESCE("Customer", '') ILIKE %(search)s
        '''
        params["search"] = f"%{search}%"

    with _connect() as conn:
        conn.set_session(readonly=True)
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(_voucher_query(where_sql=where_sql), params)
            rows = cur.fetchall()
            conn.rollback()
    return [_voucher_payload(row) for row in rows]


def _server_render_rows(vouchers):
    rows = []
    for voucher in vouchers:
        rows.append(
            "<tr>"
            f"<td>{escape(voucher['sector'])}</td>"
            f"<td>{escape(voucher['invoice_number'])}</td>"
            f"<td>{escape(voucher['customer'])}</td>"
            f"<td>{escape(voucher['invoice_date'])}</td>"
            f"<td>{voucher['voucher_total']:,}</td>"
            f"<td>{voucher['total_received']:,}</td>"
            f"<td>{voucher['outstanding_balance']:,}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def _basic_payment_page(message="", error=False):
    vouchers = _list_vouchers()
    rows = []
    for voucher in vouchers:
        key = f"{voucher['sector']}||{voucher['invoice_number']}"
        rows.append(
            "<tr>"
            f"<td><input type=\"radio\" name=\"voucher_key\" value=\"{escape(key)}\" required></td>"
            f"<td>{escape(voucher['sector'])}</td>"
            f"<td>{escape(voucher['invoice_number'])}</td>"
            f"<td>{escape(voucher['customer'])}</td>"
            f"<td>{escape(voucher['invoice_date'])}</td>"
            f"<td>{voucher['voucher_total']:,}</td>"
            f"<td>{voucher['total_received']:,}</td>"
            f"<td>{voucher['outstanding_balance']:,}</td>"
            "</tr>"
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
          section {{ background: #fff; border: 1px solid #ccc; border-radius: 6px; overflow: hidden; }}
          .side {{ padding: 14px; }}
          .table-wrap {{ max-height: calc(100vh - 120px); overflow: auto; }}
          table {{ width: 100%; border-collapse: collapse; table-layout: fixed; }}
          th, td {{ padding: 8px; border-bottom: 1px solid #ddd; text-align: left; font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
          th {{ background: #f1f3f5; }}
          input, textarea, button {{ width: 100%; box-sizing: border-box; font: inherit; padding: 8px; border-radius: 4px; border: 1px solid #bbb; }}
          button {{ margin-top: 10px; background: #176b5d; color: white; border: 0; cursor: pointer; font-weight: bold; }}
          label {{ display: block; margin: 10px 0 4px; font-size: 12px; font-weight: bold; color: #555; }}
          .ok {{ color: #176b5d; font-weight: bold; }}
          .error {{ color: #b00020; font-weight: bold; }}
          @media (max-width: 900px) {{ form {{ grid-template-columns: 1fr; }} }}
        </style>
      </head>
      <body>
        <header><h1>Receive Payment Basic</h1></header>
        <main>
          {status_html}
          <form method="post" action="/receive-payment-basic">
            <section>
              <div class="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th style="width:42px;">Pick</th>
                      <th>Sector</th>
                      <th>Invoice Number</th>
                      <th>Customer</th>
                      <th>Invoice Date</th>
                      <th>Voucher Total</th>
                      <th>Total Received</th>
                      <th>Outstanding</th>
                    </tr>
                  </thead>
                  <tbody>{"".join(rows)}</tbody>
                </table>
              </div>
            </section>
            <section class="side">
              <label>Receive Amount</label>
              <input name="receive_amount" inputmode="numeric" required>
              <label>Payment Method</label>
              <input name="payment_method" placeholder="Cash, KPay, Bank...">
              <label>Reference Number</label>
              <input name="reference_number">
              <label>Notes</label>
              <textarea name="notes" rows="5"></textarea>
              <button type="submit">Save Payment</button>
            </section>
          </form>
        </main>
      </body>
    </html>
    ''', 200, {"Cache-Control": "no-store, max-age=0"}


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
    if request.method == "GET":
        return _basic_payment_page()

    voucher_key = request.form.get("voucher_key") or ""
    if "||" not in voucher_key:
        return _basic_payment_page("Select a voucher before saving.", error=True)
    sector, invoice_number = voucher_key.split("||", 1)
    payment_method = (request.form.get("payment_method") or "").strip()
    reference_number = (request.form.get("reference_number") or "").strip()
    notes = (request.form.get("notes") or "").strip()
    try:
        receive_amount = int((request.form.get("receive_amount") or "0").replace(",", ""))
    except ValueError:
        receive_amount = 0

    if receive_amount <= 0:
        return _basic_payment_page("Receive Amount must be greater than zero.", error=True)

    voucher = _fetch_voucher(sector, invoice_number)
    if not voucher:
        return _basic_payment_page("Voucher not found.", error=True)

    previous_paid = _payment_total_received(sector, invoice_number)
    outstanding_after_payment = voucher["voucher_total"] - previous_paid - receive_amount
    _insert_payment_receive(
        sector=sector,
        voucher_number=invoice_number,
        customer=voucher["customer"],
        invoice_amount=voucher["voucher_total"],
        previous_paid=previous_paid,
        receive_amount=receive_amount,
        outstanding_balance=outstanding_after_payment,
        payment_method=payment_method,
        reference_number=reference_number,
        notes=notes,
        recorded_by="Receive Payment Basic Page",
    )
    formula_engine._update_voucher_payment_summary(sector, invoice_number)
    return _basic_payment_page("Payment saved. Totals refreshed.")


@app.get("/api/vouchers")
def list_vouchers():
    search = (request.args.get("q") or "").strip()
    return jsonify({"ok": True, "vouchers": _list_vouchers(search)})


@app.get("/api/voucher")
def get_voucher():
    sector = (request.args.get("sector") or "").strip()
    invoice_number = (request.args.get("invoice_number") or "").strip()
    if not sector or not invoice_number:
        return jsonify({"ok": False, "error": "sector and invoice_number are required"}), 400
    voucher = _fetch_voucher(sector, invoice_number)
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

    voucher = _fetch_voucher(sector, invoice_number)
    if not voucher:
        return jsonify({"ok": False, "error": "Voucher not found"}), 404

    previous_paid = _payment_total_received(sector, invoice_number)
    outstanding_after_payment = voucher["voucher_total"] - previous_paid - receive_amount
    row = _insert_payment_receive(
        sector=sector,
        voucher_number=invoice_number,
        customer=voucher["customer"],
        invoice_amount=voucher["voucher_total"],
        previous_paid=previous_paid,
        receive_amount=receive_amount,
        outstanding_balance=outstanding_after_payment,
        payment_method=payment_method,
        reference_number=reference_number,
        notes=notes,
        recorded_by=recorded_by,
    )

    formula_engine._update_voucher_payment_summary(sector, invoice_number)
    refreshed = _fetch_voucher(sector, invoice_number)
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
    formula_engine.ensure_payment_receive_table()
    formula_engine.ensure_voucher_summary_fields()
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                f'''
                INSERT INTO {formula_engine._payment_receive_table_ref()}
                  ("Receive_Date", "Sector", "Voucher_Number", "Customer", "Invoice_Amount",
                   "Previous_Paid", "Receive_Amount", "Outstanding_Balance", "Payment_Method",
                   "Reference_Number", "Notes", "Recorded_By")
                VALUES
                  (%(receive_date)s, %(sector)s, %(voucher_number)s, %(customer)s, %(invoice_amount)s,
                   %(previous_paid)s, %(receive_amount)s, %(outstanding_balance)s, %(payment_method)s,
                   %(reference_number)s, %(notes)s, %(recorded_by)s)
                RETURNING
                  id,
                  "Receive_Date" AS receive_date,
                  "Sector" AS sector,
                  "Voucher_Number" AS voucher_number,
                  "Customer" AS customer,
                  "Invoice_Amount" AS invoice_amount,
                  "Previous_Paid" AS previous_paid,
                  "Receive_Amount" AS receive_amount,
                  "Outstanding_Balance" AS outstanding_balance,
                  "Payment_Method" AS payment_method,
                  "Reference_Number" AS reference_number,
                  "Notes" AS notes,
                  "Recorded_By" AS recorded_by
                ''',
                {"receive_date": date.today(), **values},
            )
            row = dict(cur.fetchone())
        conn.commit()

    for key in ("invoice_amount", "previous_paid", "receive_amount", "outstanding_balance"):
        row[key] = _money_value(row.get(key))
    if row.get("receive_date"):
        row["receive_date"] = row["receive_date"].isoformat()
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
      border-collapse: collapse;
      table-layout: fixed;
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
        if (selected && selected.sector === v.sector && selected.invoice_number === v.invoice_number) tr.className = 'selected';
        tr.innerHTML = `
          <td>${v.sector}</td>
          <td>${v.invoice_number}</td>
          <td>${v.customer || ''}</td>
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
        const refreshed = vouchers.find(v => v.sector === selected.sector && v.invoice_number === selected.invoice_number);
        selected = refreshed || null;
        if (selected) fill(selected);
      }
      render();
    }
    async function refreshSelected() {
      if (!selected) return;
      const response = await fetch(`/api/voucher?sector=${encodeURIComponent(selected.sector)}&invoice_number=${encodeURIComponent(selected.invoice_number)}`);
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
    app.run(host="0.0.0.0", port=5060)
