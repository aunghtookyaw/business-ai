"""Single A4 renderer used by Farm Voucher Preview and downloadable PDF."""
from html import escape
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Flowable, Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate,
    Spacer, Table, TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
FONT_PATH = ROOT / "fonts/NotoSansMyanmar-Regular.ttf"
BRAND_DIR = ROOT / "static/brand-assets"
LOGO_PATH = BRAND_DIR / "logo.jpg"
TRANSPARENT_LOGO_PATH = BRAND_DIR / "logo-transparent.png"
QR_PATH = BRAND_DIR / "QR.png"
ADDRESS_PATH = BRAND_DIR / "address.txt"
PAYMENT_PATH = BRAND_DIR / "payment.txt"
FOREST = colors.HexColor("#174f36")
FOREST_DARK = colors.HexColor("#103b29")
LIME = colors.HexColor("#87bd3e")
GOLD = colors.HexColor("#d17924")
WARM_RED = colors.HexColor("#b74432")
FRESH_GREEN = colors.HexColor("#4e9a3d")
PALE_GREEN = colors.HexColor("#eaf4df")
GRID = colors.HexColor("#b7c8bd")
TEXT = colors.HexColor("#18231d")
CUSTOMER_GRID_FIELDS = (
    (("Customer Name", "customer_name"), ("Invoice Date", "invoice_date"), ("Invoice No.", "invoice_number")),
    (("Contact Address", "contact_address"), ("Contact Number", "phone_number"), ("Payment Terms", "payment_terms")),
)
HEADER_COLUMN_PROPORTIONS = (42 / 192, 56 / 192, 94 / 192)
HEADER_USABLE_WIDTH_MM = 192
HEADER_HEIGHT_MM = 28


class HeaderBanner(Flowable):
    """Compact, connected three-part brand banner drawn as one flowable."""

    def __init__(self, address_lines, width=192 * mm, height=28 * mm):
        super().__init__()
        self.address_lines = address_lines
        self.width = width
        self.height = height

    def wrap(self, available_width, available_height):
        return self.width, self.height

    def draw(self):
        canvas = self.canv
        height = self.height
        left_width = 42 * mm
        centre_width = 56 * mm
        curve_bottom_x = left_width + centre_width - 3 * mm
        curve_top_x = left_width + centre_width + 2 * mm

        # One continuous rounded banner base with a subtle fresh-lime gradient.
        canvas.saveState()
        path = canvas.beginPath()
        path.roundRect(0, 0, self.width, height, 2.5 * mm)
        canvas.clipPath(path, stroke=0, fill=0)
        steps = 36
        for index in range(steps):
            ratio = index / (steps - 1)
            color = colors.Color(
                LIME.red + (0.76 - LIME.red) * ratio,
                LIME.green + (0.88 - LIME.green) * ratio,
                LIME.blue + (0.30 - LIME.blue) * ratio,
            )
            canvas.setFillColor(color)
            canvas.rect(index * self.width / steps, 0, self.width / steps + 1, height, stroke=0, fill=1)

        # White invoice panel and logo field share the banner's vertical bounds.
        canvas.setFillColor(colors.white)
        canvas.roundRect(0.7 * mm, 0.7 * mm, left_width - 1.4 * mm, height - 1.4 * mm, 2.2 * mm, stroke=0, fill=1)
        canvas.setStrokeColor(FOREST)
        canvas.setLineWidth(0.8)
        canvas.roundRect(0.7 * mm, 0.7 * mm, left_width - 1.4 * mm, height - 1.4 * mm, 2.2 * mm, stroke=1, fill=0)

        logo_block = canvas.beginPath()
        logo_block.moveTo(left_width, 0.7 * mm)
        logo_block.lineTo(curve_bottom_x, 0.7 * mm)
        logo_block.curveTo(
            curve_bottom_x + 10 * mm, 7 * mm,
            curve_top_x - 10 * mm, 20.5 * mm,
            curve_top_x, height - 0.7 * mm,
        )
        logo_block.lineTo(left_width, height - 0.7 * mm)
        logo_block.close()
        canvas.setFillColor(colors.white)
        canvas.setStrokeColor(FOREST)
        canvas.setLineWidth(1.2)
        canvas.drawPath(logo_block, stroke=1, fill=1)

        # Flowing S-shaped white separator with a restrained gold accent.
        separator = canvas.beginPath()
        separator.moveTo(curve_bottom_x, 0.7 * mm)
        separator.curveTo(
            curve_bottom_x + 10 * mm, 7 * mm,
            curve_top_x - 10 * mm, 20.5 * mm,
            curve_top_x, height - 0.7 * mm,
        )
        canvas.setStrokeColor(colors.white)
        canvas.setLineWidth(3.0)
        canvas.drawPath(separator, stroke=1, fill=0)
        accent = canvas.beginPath()
        accent.moveTo(curve_bottom_x + 1.2 * mm, 0.9 * mm)
        accent.curveTo(
            curve_bottom_x + 11.2 * mm, 7 * mm,
            curve_top_x - 8.8 * mm, 20.5 * mm,
            curve_top_x + 1.2 * mm, height - 0.9 * mm,
        )
        canvas.setStrokeColor(GOLD)
        canvas.setLineWidth(0.8)
        canvas.drawPath(accent, stroke=1, fill=0)

        canvas.setFillColor(FOREST_DARK)
        canvas.setFont("Helvetica-Bold", 10.5)
        canvas.drawCentredString(left_width / 2, 14.2 * mm, "SALES")
        canvas.drawCentredString(left_width / 2, 9.8 * mm, "INVOICE")

        logo_path = TRANSPARENT_LOGO_PATH if TRANSPARENT_LOGO_PATH.exists() else LOGO_PATH
        logo_size = 24 * mm
        logo_x = left_width + (centre_width - logo_size - 3 * mm) / 2
        canvas.drawImage(ImageReader(str(logo_path)), logo_x, 2 * mm, logo_size, logo_size,
                         preserveAspectRatio=True, anchor="c", mask="auto")

        qr_size = 25.5 * mm
        qr_x = self.width - qr_size - 1.2 * mm
        canvas.drawImage(ImageReader(str(QR_PATH)), qr_x, (height - qr_size) / 2, qr_size, qr_size,
                         preserveAspectRatio=True, anchor="c", mask="auto")

        contact_lines = []
        if self.address_lines:
            contact_lines.append(self.address_lines[0].strip())
        for source_line in self.address_lines[1:]:
            contact_lines.extend(part.strip() for part in source_line.split(",") if part.strip())
        address_style = ParagraphStyle(
            "fv-banner-canvas-address", fontName="Helvetica", fontSize=7.5,
            leading=8.7, textColor=FOREST_DARK, alignment=TA_LEFT,
        )
        address = Paragraph("<br/>".join(escape(line) for line in contact_lines), address_style)
        address_x = curve_top_x + 4 * mm
        address_width = qr_x - address_x - 2.5 * mm
        _, address_height = address.wrap(address_width, height - 4 * mm)
        address.drawOn(canvas, address_x, (height - address_height) / 2)
        canvas.restoreState()

        # One continuous rounded outer rule visually binds every section.
        canvas.setStrokeColor(FOREST)
        canvas.setLineWidth(1.2)
        canvas.roundRect(0.4 * mm, 0.4 * mm, self.width - 0.8 * mm, height - 0.8 * mm,
                         2.3 * mm, stroke=1, fill=0)


class SignatureSpace(Flowable):
    """Reserved handwriting area with its label and rule near the bottom."""

    def __init__(self, width=97 * mm, height=38 * mm):
        super().__init__()
        self.width = width
        self.height = height

    def wrap(self, available_width, available_height):
        return self.width, self.height

    def draw(self):
        self.canv.setFillColor(TEXT)
        self.canv.setFont("Helvetica", 10.5)
        self.canv.drawString(0, 3.5 * mm, "Signature")
        self.canv.setStrokeColor(FOREST)
        self.canv.setLineWidth(0.6)
        self.canv.line(24 * mm, 3 * mm, 94 * mm, 3 * mm)


class BottomSpacer(Flowable):
    """Consume remaining frame height so the following block sits at the bottom."""

    def __init__(self, following_block):
        super().__init__()
        self.following_block = following_block
        self.needs_new_page = False

    def wrap(self, available_width, available_height):
        _, block_height = self.following_block.wrap(available_width, available_height)
        self.needs_new_page = block_height > available_height
        if self.needs_new_page:
            return available_width, available_height + 1
        return 0, max(0, available_height - block_height)

    def split(self, available_width, available_height):
        if self.needs_new_page:
            return [PageBreak(), BottomSpacer(self.following_block)]
        return []

    def draw(self):
        pass


def _text(value, fallback="-"):
    value = str(value if value is not None else "").strip()
    return value or fallback


def _money(value):
    return f"{value:,.2f} MMK"


def _number(value):
    return f"{value:,.2f}"


def _address_lines():
    return ADDRESS_PATH.read_text(encoding="utf-8").splitlines()


def _payment_lines():
    return PAYMENT_PATH.read_text(encoding="utf-8").splitlines()


def _payment_rows(lines):
    rows = []
    for line in lines:
        label, separator, value = line.partition(";")
        rows.append((label.strip(), value.strip() if separator else ""))
    return rows


def voucher_document(voucher):
    """Return the one semantic document consumed by Preview and PDF."""
    customer = voucher.get("customer_snapshot") or {}
    sections = []
    for section in voucher.get("delivery_sections") or []:
        items = []
        for line in section.get("items") or []:
            items.append({
                "date": _text(section.get("delivery_date")),
                "item": _text(line.get("description")),
                "quantity": _number(line.get("quantity")),
                "unit": _text(line.get("unit")),
                "unit_price": _money(line.get("unit_price")),
                "line_total": _money(line.get("amount")),
                "note": _text(line.get("note"), ""),
            })
        sections.append({
            "date": _text(section.get("delivery_date")),
            "items": items,
            "subtotal": _money(section.get("subtotal")),
        })
    free_items = [{
        "product": _text(line.get("description") or line.get("item") or line.get("product_code")),
        "quantity": _number(line.get("quantity")),
        "unit": _text(line.get("unit")),
        "note": _text(line.get("note"), ""),
    } for line in (voucher.get("free_lines") or [])]
    previous_total = voucher.get("total_amount")
    gross_amount = voucher.get("gross_amount", previous_total)
    net_amount = voucher.get("net_amount", previous_total)
    terms = customer.get("payment_terms_days")
    return {
        "brand_address_lines": _address_lines(),
        "payment_information_lines": _payment_lines(),
        "customer_name": _text(voucher.get("customer_name")),
        "contact_address": _text(customer.get("contact_address"), "Address not added"),
        "phone_number": _text(customer.get("phone_number")),
        "invoice_date": _text(voucher.get("voucher_date")),
        "invoice_number": _text(voucher.get("voucher_number")),
        "payment_terms": f"{int(terms)} days" if terms is not None else "Not added",
        "payment_method": _text(voucher.get("payment_method")),
        "sections": sections,
        "free_items": free_items,
        "grand_total": _money(net_amount),
        "gross_amount": _money(gross_amount),
        "discount_amount": _money(voucher.get("discount_amount", 0)),
        "cashback_amount": _money(voucher.get("cashback_amount", 0)),
        "net_amount": _money(net_amount),
        "amount_received": _money(voucher.get("amount_received")),
        "outstanding": _money(voucher.get("outstanding_balance")),
        "payment_status": _text(voucher.get("payment_status")),
        "adjustment_reason": _text(voucher.get("adjustment_reason"), ""),
        "note": _text(voucher.get("note"), "-"),
    }


def _styles():
    font = "Helvetica"
    if FONT_PATH.exists():
        if "NotoSansMyanmar" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("NotoSansMyanmar", str(FONT_PATH)))
    base = getSampleStyleSheet()
    return font, {
        "body": ParagraphStyle("fv-body", parent=base["Normal"], fontName=font, fontSize=10.5, leading=14, textColor=TEXT),
        "small": ParagraphStyle("fv-small", parent=base["Normal"], fontName=font, fontSize=8.5, leading=11, textColor=TEXT),
        "label": ParagraphStyle("fv-label", parent=base["Normal"], fontName=font, fontSize=8.5, leading=11, textColor=FOREST, spaceAfter=1),
        "value": ParagraphStyle("fv-value", parent=base["Normal"], fontName=font, fontSize=10.5, leading=14, textColor=TEXT),
        "invoice": ParagraphStyle("fv-invoice", parent=base["Normal"], fontName=font, fontSize=11, leading=14, textColor=GOLD, alignment=TA_CENTER),
        "brand": ParagraphStyle("fv-brand", parent=base["Normal"], fontName=font, fontSize=10.5, leading=14, textColor=colors.white, alignment=TA_CENTER),
        "address": ParagraphStyle("fv-address", parent=base["Normal"], fontName=font, fontSize=9, leading=13, textColor=colors.white, alignment=TA_LEFT),
        "banner_address": ParagraphStyle("fv-banner-address", parent=base["Normal"], fontName=font, fontSize=8.5, leading=12, textColor=FOREST_DARK, alignment=TA_LEFT),
        "payment_heading": ParagraphStyle("fv-payment-heading", parent=base["Normal"], fontName="Helvetica-BoldOblique", fontSize=10, leading=13, textColor=FOREST_DARK),
        "header": ParagraphStyle("fv-table-header", parent=base["Normal"], fontName=font, fontSize=9.5, leading=12, textColor=colors.white, alignment=TA_CENTER),
        "cell": ParagraphStyle("fv-cell", parent=base["Normal"], fontName=font, fontSize=9.5, leading=12, textColor=TEXT),
        "cell_right": ParagraphStyle("fv-cell-right", parent=base["Normal"], fontName=font, fontSize=9.5, leading=12, textColor=TEXT, alignment=TA_RIGHT),
        "section": ParagraphStyle("fv-section", parent=base["Normal"], fontName=font, fontSize=11.5, leading=14, textColor=FOREST_DARK),
        "total": ParagraphStyle("fv-total", parent=base["Normal"], fontName=font, fontSize=11, leading=15, textColor=TEXT, alignment=TA_RIGHT),
        "total_emphasis": ParagraphStyle("fv-total-emphasis", parent=base["Normal"], fontName=font, fontSize=11.5, leading=15, textColor=FOREST_DARK, alignment=TA_RIGHT),
        "footer": ParagraphStyle("fv-footer", parent=base["Normal"], fontName=font, fontSize=9.5, leading=12, textColor=FOREST, alignment=TA_CENTER),
    }


def _p(value, style):
    value = str(value)
    if any("\u1000" <= character <= "\u109f" for character in value) and FONT_PATH.exists():
        style = ParagraphStyle(f"{style.name}-myanmar", parent=style, fontName="NotoSansMyanmar")
    return Paragraph(escape(value).replace("\n", "<br/>"), style)


def _page(canvas, doc):
    canvas.saveState()
    width, height = A4
    canvas.setFillColor(colors.white)
    canvas.rect(0, 0, width, height, stroke=0, fill=1)
    slogan = [
        ("WE ", FOREST_DARK), ("LIVE", WARM_RED), (", WE ", FOREST_DARK),
        ("FARM", FRESH_GREEN), (", WE ", FOREST_DARK), ("ENJOY", GOLD),
    ]
    canvas.setFont("Helvetica-Bold", 8.5)
    slogan_width = sum(canvas.stringWidth(text, "Helvetica-Bold", 8.5) for text, _ in slogan)
    x = (width - slogan_width) / 2
    for text, color in slogan:
        canvas.setFillColor(color)
        canvas.drawString(x, 5.5 * mm, text)
        x += canvas.stringWidth(text, "Helvetica-Bold", 8.5)
    canvas.restoreState()


def _field(label, value, styles):
    return [_p(label.upper(), styles["label"]), _p(value, styles["value"])]


def write_farm_voucher_pdf(voucher, output_path):
    document = voucher_document(voucher)
    font, styles = _styles()
    output_path = Path(output_path)
    doc = SimpleDocTemplate(
        str(output_path), pagesize=A4, leftMargin=9 * mm, rightMargin=9 * mm,
        topMargin=8 * mm, bottomMargin=11 * mm, title=f'Sales Invoice {document["invoice_number"]}',
        author="BigShot Farm",
    )

    header = HeaderBanner(document["brand_address_lines"])

    customer_rows = [[_field(label, document[key], styles) for label, key in row] for row in CUSTOMER_GRID_FIELDS]
    customer_table = Table(customer_rows, colWidths=[82 * mm, 55 * mm, 55 * mm])
    customer_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOX", (0, 0), (-1, -1), .6, GRID), ("INNERGRID", (0, 0), (-1, -1), .35, GRID),
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))

    story = [header, Spacer(1, 4 * mm), customer_table, Spacer(1, 4 * mm)]
    widths = [25 * mm, 62 * mm, 19 * mm, 18 * mm, 33 * mm, 35 * mm]
    headers = ["Date", "Item", "Qty", "Unit", "Unit Price", "Line Total"]
    for section in document["sections"]:
        rows = [[_p(value, styles["header"]) for value in headers]]
        for item in section["items"]:
            rows.append([
                _p(item["date"], styles["cell"]), _p(item["item"] + (f'\n{item["note"]}' if item["note"] else ""), styles["cell"]),
                _p(item["quantity"], styles["cell_right"]), _p(item["unit"], styles["cell"]),
                _p(item["unit_price"], styles["cell_right"]), _p(item["line_total"], styles["cell_right"]),
            ])
        rows.append(["", "", "", "", _p("Section subtotal", styles["cell_right"]), _p(section["subtotal"], styles["cell_right"])])
        table = Table(rows, colWidths=widths, repeatRows=1, splitByRow=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), FOREST), ("BACKGROUND", (0, 1), (-1, -2), colors.white),
            ("BACKGROUND", (0, -1), (-1, -1), PALE_GREEN),
            ("GRID", (0, 0), (-1, -2), .45, GRID), ("BOX", (0, -1), (-1, -1), .6, FOREST),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        block = [_p(f'SALES DATE: {section["date"]}', styles["section"]), Spacer(1, 1.5 * mm), table, Spacer(1, 3 * mm)]
        story.append(KeepTogether(block) if len(section["items"]) <= 7 else block[0])
        if len(section["items"]) > 7:
            story.extend(block[1:])

    if document["free_items"]:
        free_headers = ["Product", "Quantity", "Unit", "Note"]
        free_rows = [[_p(value, styles["header"]) for value in free_headers]]
        for item in document["free_items"]:
            free_rows.append([
                _p(item["product"], styles["cell"]), _p(item["quantity"], styles["cell_right"]),
                _p(item["unit"], styles["cell"]), _p(item["note"], styles["cell"]),
            ])
        free_table = Table(free_rows, colWidths=[75 * mm, 30 * mm, 30 * mm, 57 * mm], repeatRows=1)
        free_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), FOREST), ("GRID", (0, 0), (-1, -1), .45, GRID),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.extend([_p("FREE ITEMS", styles["section"]), Spacer(1, 1.5 * mm), free_table, Spacer(1, 3 * mm)])

    payment_rows = _payment_rows(document["payment_information_lines"])
    payment_table = Table(
        [[_p(label, styles["body"]), _p(value, styles["body"])] for label, value in payment_rows],
        colWidths=[40 * mm, 57 * mm],
    )
    payment_table.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, -1), .4, GRID), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    amount_rows = [
        ("GROSS AMOUNT", document["gross_amount"], styles["total"]),
    ]
    if document["discount_amount"] != "0.00 MMK":
        amount_rows.append(("DISCOUNT", document["discount_amount"], styles["total"]))
    if document["cashback_amount"] != "0.00 MMK":
        amount_rows.append(("CASHBACK", document["cashback_amount"], styles["total"]))
    amount_rows.extend([
        ("NET AMOUNT", document["net_amount"], styles["total_emphasis"]),
        ("PAID", document["amount_received"], styles["total"]),
        ("TOTAL DUE", document["outstanding"], styles["total_emphasis"]),
    ])
    if document["adjustment_reason"]:
        amount_rows.append(("ADJUSTMENT REASON", document["adjustment_reason"], styles["small"]))
    amount_block = Table(
        [[_p(label, style), _p(value, style)] for label, value, style in amount_rows],
        colWidths=[34 * mm, 56 * mm],
    )
    amount_block.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, -1), .4, GRID), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    payment_left = Table([
        [_p("PLEASE MAKE PAYMENT TO:", styles["payment_heading"])],
        [payment_table],
        [SignatureSpace()],
    ], colWidths=[97 * mm])
    payment_left.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    payment = Table([[payment_left, amount_block]], colWidths=[102 * mm, 90 * mm])
    payment.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBEFORE", (1, 0), (1, 0), .6, FOREST),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.extend([BottomSpacer(payment), payment])
    doc.build(story, onFirstPage=_page, onLaterPages=_page)
    return output_path
