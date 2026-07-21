"""Professional A4 renderer for SotePhwar Sales Invoices."""
from decimal import Decimal, InvalidOperation
from pathlib import Path
import tempfile

from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from tools.farm_voucher_pdf import (
    CUSTOMER_GRID_FIELDS, FOREST, FOREST_DARK, GOLD, GRID, PALE_GREEN, TEXT,
    BottomSpacer, HeaderBanner, _field, _p, _page, _styles, voucher_document,
)


def _quantity(value):
    try:
        return Decimal(str(value or 0))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _quantity_text(value):
    value = Decimal(value)
    return str(int(value)) if value == value.to_integral_value() else f"{value:.2f}".rstrip("0").rstrip(".")


CANONICAL_BOTTLES = (
    ("4l", "4L"),
    ("1l", "1L"),
    ("500ml", "500 mL"),
    ("100ml", "100 mL"),
)


def _bottle_code(line):
    value = str(line.get("product_code") or line.get("code") or line.get("item") or line.get("description") or "")
    normalized = "".join(character for character in value.lower() if character.isalnum())
    for code, label in CANONICAL_BOTTLES:
        if normalized in {code, f"sotephwar{code}", "".join(character for character in label.lower() if character.isalnum())}:
            return code
    return None


def _bottle_quantities(voucher):
    quantities = {code: {"paid": Decimal("0"), "free": Decimal("0")} for code, _ in CANONICAL_BOTTLES}
    for kind, lines in (
        ("paid", voucher.get("paid_lines") or voucher.get("lines") or []),
        ("free", voucher.get("free_lines") or []),
    ):
        for line in lines:
            code = _bottle_code(line)
            if code:
                quantities[code][kind] += _quantity(line.get("quantity"))
    return quantities


def _write_layout(voucher, output_path):
    document = voucher_document(voucher)
    _, styles = _styles()
    doc = SimpleDocTemplate(
        str(output_path), pagesize=A4, leftMargin=9 * mm, rightMargin=9 * mm,
        topMargin=8 * mm, bottomMargin=11 * mm,
        title=f'SotePhwar Sales Invoice {document["invoice_number"]}', author="BigShot SotePhwar",
    )

    # Header, customer information, and Sales Items are intentionally identical
    # to the established BigShot invoice layout.
    header = HeaderBanner(document["brand_address_lines"])
    customer_rows = [[_field(label, document[key], styles) for label, key in row] for row in CUSTOMER_GRID_FIELDS]
    customer_table = Table(customer_rows, colWidths=[82 * mm, 55 * mm, 55 * mm])
    customer_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOX", (0, 0), (-1, -1), .6, GRID),
        ("INNERGRID", (0, 0), (-1, -1), .35, GRID), ("BACKGROUND", (0, 0), (-1, -1), colors.white),
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
            ("BACKGROUND", (0, -1), (-1, -1), PALE_GREEN), ("GRID", (0, 0), (-1, -2), .45, GRID),
            ("BOX", (0, -1), (-1, -1), .6, FOREST), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        block = [_p(f'SALES DATE: {section["date"]}', styles["section"]), Spacer(1, 1.5 * mm), table, Spacer(1, 3 * mm)]
        story.extend([KeepTogether(block)] if len(section["items"]) <= 7 else block)

    story.extend([_p("FREE ITEMS", styles["section"]), Spacer(1, 1 * mm)])

    if document["free_items"]:
        free_rows = [[_p(value, styles["header"]) for value in ("Product", "Quantity", "Unit", "Note")]]
        for item in document["free_items"]:
            free_rows.append([_p(item["product"], styles["cell"]), _p(item["quantity"], styles["cell_right"]), _p(item["unit"], styles["cell"]), _p(item["note"], styles["cell"])])
        free_table = Table(free_rows, colWidths=[75 * mm, 30 * mm, 30 * mm, 57 * mm], repeatRows=1)
        free_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), FOREST), ("GRID", (0, 0), (-1, -1), .4, GRID),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4), ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.extend([free_table, Spacer(1, 3 * mm)])
    else:
        empty_style = ParagraphStyle("sp-free-empty", parent=styles["small"], textColor=TEXT)
        empty = Table([[_p("No promotional free items.", empty_style)]], colWidths=[192 * mm])
        empty.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f7faf5")), ("BOX", (0, 0), (-1, -1), .4, GRID), ("LEFTPADDING", (0, 0), (-1, -1), 7), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
        story.extend([empty, Spacer(1, 3 * mm)])

    summary_heading = ParagraphStyle(
        "sp-summary-heading", parent=styles["section"], fontName="Helvetica-Bold",
        fontSize=12, leading=14, textColor=FOREST_DARK,
    )
    summary_header = ParagraphStyle(
        "sp-summary-header", parent=styles["header"], fontName="Helvetica-Bold",
        fontSize=10, leading=12,
    )
    summary_cell = ParagraphStyle(
        "sp-summary-cell", parent=styles["cell"], fontSize=10, leading=12,
    )
    summary_number = ParagraphStyle(
        "sp-summary-number", parent=summary_cell, alignment=TA_RIGHT,
    )
    quantities = _bottle_quantities(voucher)
    summary_rows = [[_p(value, summary_header) for value in ("Bottle Type", "Paid Qty", "Free Qty", "Total Qty")]]
    for code, label in CANONICAL_BOTTLES:
        paid = quantities[code]["paid"]
        free = quantities[code]["free"]
        summary_rows.append([
            _p(label, summary_cell), _p(_quantity_text(paid), summary_number),
            _p(_quantity_text(free), summary_number), _p(_quantity_text(paid + free), summary_number),
        ])
    bottle_summary = Table(summary_rows, colWidths=[75 * mm, 39 * mm, 39 * mm, 39 * mm], repeatRows=1)
    bottle_summary.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), FOREST), ("BACKGROUND", (0, 1), (-1, -1), colors.white),
        ("GRID", (0, 0), (-1, -1), .4, GRID), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.extend([_p("BOTTLE SUMMARY", summary_heading), Spacer(1, 1 * mm), bottle_summary, Spacer(1, 3 * mm)])

    finance_label = ParagraphStyle("sp-finance-label", parent=styles["small"], fontName="Helvetica-Bold", alignment=TA_RIGHT, textColor=FOREST_DARK)
    finance_value = ParagraphStyle("sp-finance-value", parent=styles["body"], alignment=TA_RIGHT, textColor=TEXT)
    finance_net = ParagraphStyle("sp-finance-net", parent=finance_value, fontName="Helvetica-Bold", textColor=FOREST_DARK)
    amounts = [
        ("GROSS AMOUNT", document["gross_amount"], finance_value), ("DISCOUNT", document["discount_amount"], finance_value),
        ("CASHBACK", document["cashback_amount"], finance_value), ("NET AMOUNT", document["net_amount"], finance_net),
        ("RECEIVED", document["amount_received"], finance_value), ("OUTSTANDING", document["outstanding"], finance_value),
    ]
    if document["adjustment_reason"]:
        amounts.append(("ADJUSTMENT REASON", document["adjustment_reason"], styles["small"]))
    finance_heading = ParagraphStyle("sp-finance-heading", parent=styles["section"], fontName="Helvetica-Bold", textColor=colors.white)
    finance_rows = [[_p("FINANCIAL SUMMARY", finance_heading), ""]] + [[_p(label, finance_label), _p(value, style)] for label, value, style in amounts]
    finance = Table(finance_rows, colWidths=[105 * mm, 87 * mm])
    finance.setStyle(TableStyle([
        ("SPAN", (0, 0), (-1, 0)), ("BACKGROUND", (0, 0), (-1, 0), FOREST),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("BOX", (0, 0), (-1, -1), .7, FOREST),
        ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f5faf2")), ("LINEBELOW", (0, 1), (-1, -2), .35, GRID),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))

    signature_style = ParagraphStyle("sp-signature", parent=styles["small"], alignment=TA_CENTER, textColor=FOREST_DARK)
    signature_blocks = []
    for label in ("Customer", "Warehouse", "Delivery", "Sales Representative"):
        block = Table([[""], [_p(label, signature_style)]], colWidths=[43 * mm], rowHeights=[12 * mm, 6 * mm])
        block.setStyle(TableStyle([("LINEABOVE", (0, 1), (0, 1), .55, FOREST), ("VALIGN", (0, 0), (-1, -1), "BOTTOM")]))
        signature_blocks.append(block)
    signatures = Table([signature_blocks], colWidths=[48 * mm] * 4)
    signatures.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER"), ("LEFTPADDING", (0, 0), (-1, -1), 2.5 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 2.5 * mm)]))
    story.extend([finance, BottomSpacer(signatures), KeepTogether(signatures)])
    doc.build(story, onFirstPage=_page, onLaterPages=_page)


def write_sotephwar_voucher_pdf(voucher, output_path):
    """Render the commercial layout and preserve the approved SotePhwar header."""
    output_path = Path(output_path)
    with tempfile.TemporaryDirectory() as directory:
        base_path = Path(directory) / "base.pdf"
        overlay_path = Path(directory) / "heading.pdf"
        _write_layout(voucher, base_path)
        canvas = Canvas(str(overlay_path), pagesize=A4)
        _, height = A4
        x, y, width, box_height = 11 * mm, height - 37.3 * mm, 41.2 * mm, 27.2 * mm
        canvas.setFillColor(colors.white); canvas.setStrokeColor(FOREST); canvas.setLineWidth(0.8)
        canvas.roundRect(x, y, width, box_height, 2.2 * mm, stroke=1, fill=1)
        canvas.setFillColor(FOREST_DARK); canvas.setFont("Helvetica-Bold", 10.5)
        centre = x + width / 2
        canvas.drawCentredString(centre, y + 16.0 * mm, "SOTEPHWAR")
        canvas.drawCentredString(centre, y + 11.6 * mm, "SALES")
        canvas.drawCentredString(centre, y + 7.2 * mm, "INVOICE")
        canvas.save()
        overlay = PdfReader(str(overlay_path)).pages[0]
        writer = PdfWriter(clone_from=str(base_path)); writer.pages[0].merge_page(overlay)
        writer.add_metadata({"/Title": f'SotePhwar Sales Invoice {voucher.get("voucher_number", "")}', "/Author": "BigShot SotePhwar"})
        with output_path.open("wb") as handle: writer.write(handle)
    return output_path


__all__ = ["voucher_document", "write_sotephwar_voucher_pdf"]
