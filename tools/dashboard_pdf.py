from datetime import datetime
from pathlib import Path

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from tools.pdf_utils import ensure_myanmar_font_registered, font_for_text


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_LOGO = PROJECT_ROOT / "dashboard-prototype" / "assets" / "bigshot-logo.jpg"

PAGE_WIDTH, PAGE_HEIGHT = landscape(A4)
BRAND = (23, 79, 59)
BRAND_2 = (38, 119, 90)
BRAND_SOFT = (228, 240, 234)
TEXT = (31, 41, 55)
MUTED = (107, 114, 128)
LINE = (222, 226, 232)
SURFACE = (255, 255, 255)
SURFACE_2 = (247, 249, 252)
GOLD = (199, 139, 40)
NEGATIVE = (190, 66, 66)


def _rgb(pdf, color, stroke=False):
    setter = pdf.setStrokeColorRGB if stroke else pdf.setFillColorRGB
    setter(*(component / 255 for component in color))


def _money(value):
    try:
        number = int(value or 0)
    except (TypeError, ValueError):
        return "-"
    return f"{number:,} MMK"


def _short_money(value):
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return "-"
    absolute = abs(number)
    if absolute >= 1_000_000_000:
        return f"{number / 1_000_000_000:.2f}B"
    if absolute >= 1_000_000:
        return f"{number / 1_000_000:.1f}M"
    if absolute >= 1_000:
        return f"{number / 1_000:.1f}K"
    return f"{int(number):,}"


def _text(pdf, x, y, value, size=9, bold=False, color=TEXT, max_chars=None):
    text = "-" if value in (None, "") else str(value)
    if max_chars and len(text) > max_chars:
        text = text[: max_chars - 3].rstrip() + "..."
    font = font_for_text(text)
    if font == "Helvetica" and bold:
        font = "Helvetica-Bold"
    _rgb(pdf, color)
    pdf.setFont(font, size)
    pdf.drawString(x, y, text)


def _right_text(pdf, x, y, value, size=9, bold=False, color=TEXT):
    text = "-" if value in (None, "") else str(value)
    font = font_for_text(text)
    if font == "Helvetica" and bold:
        font = "Helvetica-Bold"
    _rgb(pdf, color)
    pdf.setFont(font, size)
    pdf.drawRightString(x, y, text)


def _rect(pdf, x, y, width, height, fill=SURFACE, stroke=LINE, radius=7):
    if fill:
        _rgb(pdf, fill)
    if stroke:
        _rgb(pdf, stroke, stroke=True)
    pdf.roundRect(x, y, width, height, radius, fill=1 if fill else 0, stroke=1 if stroke else 0)


def _card(pdf, x, y, width, height, label, value, note="", featured=False, alert=False):
    fill = BRAND if featured else SURFACE
    stroke = BRAND if featured else LINE
    _rect(pdf, x, y, width, height, fill=fill, stroke=stroke)
    if alert:
        _rgb(pdf, NEGATIVE)
        pdf.rect(x, y + height - 3, width, 3, fill=1, stroke=0)
    label_color = (205, 231, 218) if featured else MUTED
    value_color = (255, 255, 255) if featured else TEXT
    note_color = (190, 242, 212) if featured else MUTED
    _text(pdf, x + 12, y + height - 24, label, size=7.8, bold=True, color=label_color, max_chars=26)
    _text(pdf, x + 12, y + 34, value, size=15, bold=True, color=value_color, max_chars=18)
    _text(pdf, x + 12, y + 16, note, size=7.4, color=note_color, max_chars=28)


def _panel_title(pdf, x, y, eyebrow, title, chip=None):
    _text(pdf, x, y, eyebrow.upper(), size=6.8, bold=True, color=BRAND_2)
    _text(pdf, x, y - 15, title, size=11, bold=True, color=TEXT)
    if chip:
        _rect(pdf, x + 235, y - 18, 56, 16, fill=BRAND_SOFT, stroke=None, radius=8)
        _text(pdf, x + 244, y - 13, chip, size=6.6, bold=True, color=BRAND)


def _line_chart(pdf, x, y, width, height, trend):
    _rect(pdf, x, y, width, height, fill=SURFACE, stroke=LINE)
    _panel_title(pdf, x + 14, y + height - 20, "Revenue", "Financial trend", "BI API")
    chart_x = x + 42
    chart_y = y + 30
    chart_w = width - 62
    chart_h = height - 78
    series = []
    for key, color in (("revenue", BRAND_2), ("expense", GOLD), ("profit", (143, 165, 154))):
        values = [float(row.get(key) or 0) for row in trend]
        if values:
            series.extend(values)
        _rgb(pdf, color, stroke=True)
        pdf.setLineWidth(1.8 if key != "profit" else 1.2)
        if key == "profit":
            pdf.setDash(4, 4)
        else:
            pdf.setDash()
        _draw_series(pdf, chart_x, chart_y, chart_w, chart_h, values, min(series or [0]), max(series or [1]))
    pdf.setDash()
    for idx, row in enumerate(trend[:8]):
        if not trend:
            break
        label_x = chart_x + (idx * chart_w / max(len(trend[:8]) - 1, 1))
        _text(pdf, label_x - 8, y + 12, row.get("label", ""), size=6.5, color=MUTED, max_chars=6)
    legend_x = x + width - 170
    for label, color in (("Revenue", BRAND_2), ("Expense", GOLD), ("Profit", (143, 165, 154))):
        _rgb(pdf, color)
        pdf.circle(legend_x, y + height - 26, 3, fill=1, stroke=0)
        _text(pdf, legend_x + 7, y + height - 29, label, size=6.8, color=MUTED)
        legend_x += 54


def _draw_series(pdf, x, y, width, height, values, minimum, maximum):
    if not values:
        return
    value_range = maximum - minimum or 1
    points = []
    for index, value in enumerate(values[:8]):
        px = x + (index * width / max(len(values[:8]) - 1, 1))
        py = y + ((value - minimum) / value_range * height)
        points.append((px, py))
    path = pdf.beginPath()
    path.moveTo(*points[0])
    for point in points[1:]:
        path.lineTo(*point)
    pdf.drawPath(path, stroke=1, fill=0)


def _spark_panel(pdf, x, y, width, height, eyebrow, title, rows):
    _rect(pdf, x, y, width, height, fill=SURFACE, stroke=LINE)
    _panel_title(pdf, x + 14, y + height - 20, eyebrow, title)
    row_y = y + height - 58
    for label, value, color in rows:
        _text(pdf, x + 14, row_y, label, size=7.6, bold=True, color=MUTED, max_chars=24)
        _right_text(pdf, x + width - 14, row_y, value, size=8.2, bold=True, color=color)
        row_y -= 21


def _rank_panel(pdf, x, y, width, height, eyebrow, title, rows, label_key, value_key, detail_key=None):
    _rect(pdf, x, y, width, height, fill=SURFACE, stroke=LINE)
    _panel_title(pdf, x + 14, y + height - 20, eyebrow, title)
    row_y = y + height - 58
    for index, row in enumerate(rows[:6], start=1):
        _rect(pdf, x + 14, row_y - 5, 18, 15, fill=BRAND_SOFT, stroke=None, radius=7)
        _text(pdf, x + 18, row_y, str(index).zfill(2), size=6.5, bold=True, color=BRAND)
        label = row.get(label_key) or row.get("item") or "-"
        _text(pdf, x + 40, row_y + 1, label, size=7.6, bold=True, max_chars=28)
        if detail_key:
            _text(pdf, x + 40, row_y - 10, row.get(detail_key) or "", size=6.5, color=MUTED, max_chars=28)
        _right_text(pdf, x + width - 14, row_y, _short_money(row.get(value_key)), size=7.6, bold=True)
        row_y -= 27
    if not rows:
        _text(pdf, x + 14, y + height - 62, "No rows match the selected scope.", size=8, color=MUTED)


def _inventory_panel(pdf, x, y, width, height, inventory):
    rows = inventory.get("locations") or []
    if not rows:
        grouped = {}
        for row in inventory.get("stock") or []:
            store = row.get("store") or "-"
            grouped.setdefault(store, {"store": store, "current_qty": 0, "inventory_value": 0})
            grouped[store]["current_qty"] += int(row.get("stock_qty") or row.get("qty") or 0)
            grouped[store]["inventory_value"] += int(row.get("inventory_value") or 0)
        rows = sorted(grouped.values(), key=lambda item: item["inventory_value"], reverse=True)
    _rect(pdf, x, y, width, height, fill=SURFACE, stroke=LINE)
    _panel_title(pdf, x + 14, y + height - 20, "Inventory", "Stock by location")
    max_value = max([int(row.get("inventory_value") or 0) for row in rows[:6]] + [1])
    row_y = y + height - 58
    for row in rows[:6]:
        store = row.get("store") or "-"
        qty = int(row.get("current_qty") or row.get("qty") or 0)
        value = int(row.get("inventory_value") or 0)
        _text(pdf, x + 14, row_y + 2, f"{store} · {qty:,} units", size=7.4, bold=True, max_chars=34)
        _right_text(pdf, x + width - 14, row_y + 2, _money(value), size=7.4, bold=True)
        bar_w = (width - 28) * value / max_value
        _rgb(pdf, BRAND_2)
        pdf.roundRect(x + 14, row_y - 9, bar_w, 4, 2, fill=1, stroke=0)
        _rgb(pdf, (229, 234, 241))
        pdf.roundRect(x + 14 + bar_w, row_y - 9, width - 28 - bar_w, 4, 2, fill=1, stroke=0)
        row_y -= 25
    if not rows:
        _text(pdf, x + 14, y + height - 62, "No inventory rows match the selected scope.", size=8, color=MUTED)


def _table_panel(pdf, x, y, width, height, eyebrow, title, headers, rows):
    _rect(pdf, x, y, width, height, fill=SURFACE, stroke=LINE)
    _panel_title(pdf, x + 14, y + height - 20, eyebrow, title)
    col_w = [width * item for item in (0.34, 0.22, 0.22, 0.22)]
    table_y = y + height - 58
    _rect(pdf, x + 14, table_y - 6, width - 28, 18, fill=(234, 239, 246), stroke=None, radius=3)
    current_x = x + 20
    for index, header in enumerate(headers):
        _text(pdf, current_x, table_y, header, size=6.8, bold=True, color=MUTED)
        current_x += col_w[index]
    table_y -= 24
    for row in rows[:5]:
        current_x = x + 20
        for index, value in enumerate(row):
            _text(pdf, current_x, table_y, value, size=7.2, bold=index == 0, max_chars=22 if index == 0 else 14)
            current_x += col_w[index]
        table_y -= 18


def write_dashboard_pdf(data, output_path, title="BigShot Executive Dashboard"):
    ensure_myanmar_font_registered()
    pdf = canvas.Canvas(str(output_path), pagesize=(PAGE_WIDTH, PAGE_HEIGHT), pageCompression=0, invariant=1)
    pdf.setTitle(title)
    _rgb(pdf, (244, 247, 251))
    pdf.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, fill=1, stroke=0)

    if DASHBOARD_LOGO.exists():
        pdf.drawImage(ImageReader(str(DASHBOARD_LOGO)), 34, PAGE_HEIGHT - 72, width=46, height=46, preserveAspectRatio=True, mask="auto")
    _text(pdf, 92, PAGE_HEIGHT - 42, title, size=18, bold=True)
    _text(pdf, 92, PAGE_HEIGHT - 58, data.get("filter_label") or "-", size=8.5, color=MUTED)
    _right_text(pdf, PAGE_WIDTH - 34, PAGE_HEIGHT - 42, f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}", size=7.6, color=MUTED)
    _right_text(pdf, PAGE_WIDTH - 34, PAGE_HEIGHT - 58, "Canonical Formula Engine", size=7.6, bold=True, color=BRAND)

    metrics = data.get("metrics") or {}
    card_y = PAGE_HEIGHT - 145
    card_w = 124
    gap = 9
    cards = [
        ("Revenue", _money(metrics.get("revenue")), data.get("filter_label", ""), True, False),
        ("Expenses", _money(metrics.get("expenses")), "Transection expenses", False, False),
        ("Net Profit", _money(metrics.get("net_profit")), f"{metrics.get('profit_margin_percent') or 0}% profit margin", False, False),
        ("Cash Received", _money(metrics.get("cash_received")), "Canonical cash inflow", False, False),
        ("Outstanding", _money(metrics.get("outstanding_receivables")), "Collection focus", False, True),
        ("Inventory Value", _money(metrics.get("inventory_value")), "Formula Engine valuation", False, False),
    ]
    for index, (label, value, note, featured, alert) in enumerate(cards):
        _card(pdf, 34 + index * (card_w + gap), card_y, card_w, 72, label, value, note, featured=featured, alert=alert)

    _line_chart(pdf, 34, 220, 520, 235, data.get("trend") or [])
    _spark_panel(pdf, 570, 338, 236, 117, "Cash", "Cash flow position", [
        ("Net Cash", _money((data.get("cash_flow") or {}).get("net_cash_flow")), NEGATIVE if int((data.get("cash_flow") or {}).get("net_cash_flow") or 0) < 0 else BRAND),
        ("Inflow", _money((data.get("cash_flow") or {}).get("total_inflow")), BRAND),
        ("Outflow", _money((data.get("cash_flow") or {}).get("total_outflow")), GOLD),
    ])
    receivables = data.get("receivables") or {}
    _spark_panel(pdf, 570, 220, 236, 103, "Collections", "Receivable status", [
        ("Collection Rate", f"{receivables.get('collection_rate_percent') or 0}%", BRAND),
        ("Received", _money(receivables.get("total_received")), BRAND),
        ("Outstanding", _money(receivables.get("outstanding_receivables")), NEGATIVE),
    ])

    _inventory_panel(pdf, 34, 36, 250, 164, data.get("inventory") or {})
    _rank_panel(pdf, 300, 36, 244, 164, "Expense Control", "Top expense categories", data.get("top_expense_categories") or [], "category", "amount", "transaction_count")
    _rank_panel(pdf, 560, 36, 246, 164, "Products", "Top products", data.get("top_products") or [], "product", "total_amount", "quantity")

    pdf.showPage()
    _rgb(pdf, (244, 247, 251))
    pdf.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, fill=1, stroke=0)
    _text(pdf, 34, PAGE_HEIGHT - 42, "Dashboard Detail Tables", size=17, bold=True)
    _text(pdf, 34, PAGE_HEIGHT - 58, data.get("filter_label") or "-", size=8.5, color=MUTED)
    customers = [
        (
            row.get("customer_name") or row.get("item") or "-",
            _money(row.get("total_amount") or row.get("amount")),
            _money(row.get("amount_received")),
            _money(row.get("outstanding_amount")),
        )
        for row in (data.get("top_customers") or [])
    ]
    payments = [
        (
            row.get("receive_date") or "-",
            row.get("customer") or "-",
            row.get("voucher_number") or "-",
            _money(row.get("receive_amount")),
        )
        for row in (data.get("recent_payments") or [])
    ]
    transactions = [
        (
            row.get("date") or "-",
            row.get("income_expense") or "-",
            row.get("category") or row.get("sector") or "-",
            _money(row.get("amount")),
        )
        for row in (data.get("recent_transactions") or [])
    ]
    _table_panel(pdf, 34, 318, 372, 210, "Customers", "Top customers", ("Customer", "Total", "Received", "Outstanding"), customers)
    _table_panel(pdf, 422, 318, 384, 210, "Payments", "Recent payments", ("Date", "Customer", "Voucher", "Amount"), payments)
    _table_panel(pdf, 34, 78, 772, 210, "Activity", "Recent transactions", ("Date", "Type", "Category", "Amount"), transactions)
    _text(pdf, 34, 36, "Dashboard PDF mirrors the browser dashboard and uses the same Formula Engine data payload.", size=7.5, color=MUTED)
    pdf.save()
    return True
