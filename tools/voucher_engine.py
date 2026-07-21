"""Shared voucher workflow domain layer.

This module deliberately performs no database writes. Draft persistence and atomic
submission are adapters layered on top of this validated domain contract.
"""
from copy import deepcopy
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


WORKFLOW = ("draft", "validated", "previewed", "submitted")
SECTORS = {"farm": "Farm", "sotephwar": "Sote Phwar"}
PAYMENT_METHODS = ("Cash", "KPay", "AYA Pay", "UAB Pay", "Other Online Pay")
SOTEPHWAR_PRODUCTS = {
    "4l": {"item": "Sote Phwar 4L", "default_selling_price": Decimal("120000.00")},
    "1l": {"item": "Sote Phwar 1L", "default_selling_price": Decimal("33000.00")},
    "500ml": {"item": "Sote Phwar 500 mL", "default_selling_price": Decimal("17000.00")},
    "100ml": {"item": "Sote Phwar 100 mL", "default_selling_price": Decimal("5000.00")},
}


class VoucherValidationError(ValueError):
    def __init__(self, errors):
        self.errors = errors
        super().__init__("; ".join(errors))


def _text(value):
    return str(value or "").strip()


def _decimal(value, field, errors, positive=False):
    try:
        result = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        errors.append(f"{field} must be a number")
        return Decimal("0")
    if positive and result <= 0:
        errors.append(f"{field} must be greater than zero")
    return result


def _adjustments(voucher, gross_amount, errors):
    discount = _decimal(voucher.get("discount_amount", 0), "discount_amount", errors)
    cashback = _decimal(voucher.get("cashback_amount", 0), "cashback_amount", errors)
    for field, value in (("discount_amount", discount), ("cashback_amount", cashback)):
        if value < 0:
            errors.append(f"{field} cannot be negative")
        if value != value.to_integral_value():
            errors.append(f"{field} must be a whole MMK amount")
    net = gross_amount - discount - cashback
    if net < 0:
        errors.append("discount_amount plus cashback_amount cannot exceed gross_amount")
    voucher.update({
        "gross_amount": gross_amount, "discount_amount": discount,
        "cashback_amount": cashback, "net_amount": net,
        "adjustment_reason": _text(voucher.get("adjustment_reason")),
    })
    return net


def new_draft(sector="farm"):
    if sector not in SECTORS:
        raise ValueError("sector must be farm or sotephwar")
    return {
        "sector": sector, "status": "draft", "voucher_number": "",
        "voucher_date": date.today().isoformat(), "customer_id": None,
        "customer_name": "", "customer_snapshot": {}, "payment_method": "", "note": "", "amount_received": "0",
        "delivery_sections": [], "lines": [], "discount_amount": "0",
        "cashback_amount": "0", "adjustment_reason": "", "free_lines": [],
    }


def _section_source(voucher):
    sections = voucher.get("delivery_sections")
    if isinstance(sections, list) and sections:
        return sections
    lines = voucher.get("lines") or []
    if isinstance(lines, list) and lines:
        items = []
        for source in lines:
            line = deepcopy(source or {})
            crop_id = line.get("crop_id")
            custom = _text(line.get("custom_description") or line.get("description") or line.get("item"))
            line.update({
                "crop_id": crop_id,
                "custom_description": "" if crop_id else custom,
                "crop_name": _text(line.get("crop_name") or (line.get("description") if crop_id else "")),
            })
            items.append(line)
        return [{"delivery_date": voucher.get("voucher_date"), "items": items}]
    return []


def validate(draft):
    """Normalize and validate a Farm or Sote Phwar voucher without side effects."""
    voucher = deepcopy(draft or {})
    errors = []
    sector = _text(voucher.get("sector")).lower()
    if sector not in SECTORS:
        errors.append("sector must be farm or sotephwar")
    voucher["sector"] = sector
    voucher["voucher_number"] = _text(voucher.get("voucher_number"))
    voucher["customer_name"] = _text(voucher.get("customer_name"))
    voucher["payment_method"] = _text(voucher.get("payment_method"))
    voucher["note"] = _text(voucher.get("note"))
    if not voucher["voucher_number"]:
        errors.append("voucher_number is required")
    if sector == "farm" and voucher["voucher_number"] and not voucher["voucher_number"].isdigit():
        errors.append("Farm voucher_number must contain digits only")
    if not voucher["customer_name"] and not voucher.get("customer_id"):
        errors.append("customer is required")
    if voucher["payment_method"] not in PAYMENT_METHODS:
        errors.append("payment_method must be Cash, KPay, AYA Pay, UAB Pay, or Other Online Pay")
    try:
        voucher["voucher_date"] = date.fromisoformat(_text(voucher.get("voucher_date"))).isoformat()
    except ValueError:
        errors.append("voucher_date must use YYYY-MM-DD")
    raw_sections = _section_source(voucher)
    if not raw_sections:
        errors.append("at least one delivery date section is required")
    merged = {}
    for section_index, source_section in enumerate(raw_sections, 1):
        section = deepcopy(source_section or {})
        try:
            delivery_date = date.fromisoformat(_text(section.get("delivery_date"))).isoformat()
        except ValueError:
            errors.append(f"section {section_index} delivery_date is required and must use YYYY-MM-DD")
            delivery_date = _text(section.get("delivery_date")) or f"invalid-{section_index}"
        items = section.get("items") or []
        if not isinstance(items, list) or not items:
            errors.append(f"section {section_index} requires at least one item")
            items = []
        merged.setdefault(delivery_date, []).extend(items)

    normalized_sections = []
    normalized_lines = []
    for section_index, delivery_date in enumerate(sorted(merged), 1):
        normalized_items = []
        for item_index, source in enumerate(merged[delivery_date], 1):
            line = deepcopy(source or {})
            crop_id = line.get("crop_id")
            try:
                crop_id = int(crop_id) if crop_id not in (None, "") else None
            except (TypeError, ValueError):
                crop_id = None
                errors.append(f"section {section_index} item {item_index} crop_id must be an integer")
            custom = _text(line.get("custom_description"))
            crop_name = _text(line.get("crop_name"))
            if bool(crop_id) == bool(custom):
                errors.append(f"section {section_index} item {item_index} requires exactly one crop or custom item")
            if crop_id and not crop_name:
                errors.append(f"section {section_index} item {item_index} crop name is unavailable")
            description = custom or crop_name
            quantity = _decimal(line.get("quantity"), f"section {section_index} item {item_index} quantity", errors, positive=True)
            unit = _text(line.get("unit"))
            if not unit:
                errors.append(f"section {section_index} item {item_index} unit is required")
            unit_price = _decimal(line.get("unit_price"), f"section {section_index} item {item_index} unit_price", errors)
            if unit_price < 0:
                errors.append(f"section {section_index} item {item_index} unit_price cannot be negative")
            amount = (quantity * unit_price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            normalized = {
                "crop_id": crop_id, "crop_name": crop_name if crop_id else "",
                "custom_description": custom if not crop_id else "", "description": description,
                "quantity": quantity, "unit": unit, "unit_price": unit_price,
                "amount": amount, "note": _text(line.get("note")),
            }
            normalized_items.append(normalized)
            normalized_lines.append({**normalized, "delivery_date": delivery_date})
        subtotal = sum((item["amount"] for item in normalized_items), Decimal("0"))
        normalized_sections.append({"delivery_date": delivery_date, "items": normalized_items, "subtotal": subtotal})
    if errors:
        raise VoucherValidationError(errors)
    voucher["lines"] = normalized_lines
    voucher["delivery_sections"] = normalized_sections
    voucher["status"] = "validated"
    return voucher


def preview(draft):
    voucher = validate(draft)
    voucher["subtotal"] = sum((section["subtotal"] for section in voucher["delivery_sections"]), Decimal("0"))
    errors = []
    voucher["total_amount"] = _adjustments(voucher, voucher["subtotal"], errors)
    voucher["amount_received"] = _decimal(voucher.get("amount_received", 0), "amount_received", errors)
    if voucher["amount_received"] < 0:
        errors.append("amount_received cannot be negative")
    if voucher["amount_received"] > voucher["net_amount"]:
        errors.append("amount_received cannot exceed net_amount")
    if errors:
        raise VoucherValidationError(errors)
    voucher["outstanding_balance"] = voucher["total_amount"] - voucher["amount_received"]
    voucher["payment_status"] = (
        "Paid" if voucher["outstanding_balance"] == 0 else
        "Partial" if voucher["amount_received"] > 0 else "Outstanding"
    )
    voucher["status"] = "previewed"
    voucher["print_title"] = f'{SECTORS[voucher["sector"]]} Voucher'
    return voucher


def farm_transaction_rows(draft):
    """Map a Farm voucher to the accounting summary stored in farm_transection."""
    voucher = preview(draft)
    if voucher["sector"] != "farm":
        raise ValueError("farm_transaction_rows requires a Farm voucher")
    return [{
        "Date": voucher["voucher_date"],
        "Invoice_Number": voucher["voucher_number"],
        "Customer": voucher["customer_name"],
        "Total_Amount": voucher["total_amount"],
        "Total_Received": voucher["amount_received"],
        "Outstanding_Balance": voucher["outstanding_balance"],
        "Payment_Status": voucher["payment_status"],
    }]


def validate_sotephwar(draft):
    """Normalize fixed-product SotePhwar voucher lines without side effects."""
    voucher = deepcopy(draft or {})
    errors = []
    if _text(voucher.get("sector")).lower() != "sotephwar":
        errors.append("sector must be sotephwar")
    voucher["sector"] = "sotephwar"
    voucher["voucher_number"] = _text(voucher.get("voucher_number"))
    voucher["customer_name"] = _text(voucher.get("customer_name"))
    voucher["payment_method"] = _text(voucher.get("payment_method"))
    voucher["note"] = _text(voucher.get("note"))
    if not voucher["voucher_number"]:
        errors.append("voucher_number is required")
    if not voucher["customer_name"] and not voucher.get("customer_id"):
        errors.append("customer is required")
    try:
        voucher["voucher_date"] = date.fromisoformat(_text(voucher.get("voucher_date"))).isoformat()
    except ValueError:
        errors.append("voucher_date must use YYYY-MM-DD")

    source_lines = voucher.get("lines") or []
    if not isinstance(source_lines, list) or not source_lines:
        errors.append("at least one product line is required")
        source_lines = []
    lines = []
    for index, source in enumerate(source_lines, 1):
        line = deepcopy(source or {})
        code = _text(line.get("product_code")).lower()
        product = SOTEPHWAR_PRODUCTS.get(code)
        if not product:
            errors.append(f"line {index} product_code is invalid")
        quantity = _decimal(line.get("quantity"), f"line {index} quantity", errors, positive=True)
        if quantity != quantity.to_integral_value():
            errors.append(f"line {index} quantity must be a whole number of bottles")
        unit_price = _decimal(line.get("unit_price"), f"line {index} unit_price", errors)
        if unit_price < 0:
            errors.append(f"line {index} unit_price cannot be negative")
        amount = (quantity * unit_price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if amount != amount.to_integral_value():
            errors.append(f"line {index} total must be a whole MMK amount")
        lines.append({
            "product_code": code,
            "item": product["item"] if product else "",
            "description": product["item"] if product else "",
            "quantity": quantity,
            "unit": "bottle",
            "unit_price": unit_price,
            "amount": amount,
            "note": _text(line.get("note")),
        })
    free_lines = []
    seen_free = set()
    source_free = voucher.get("free_lines") or []
    if not isinstance(source_free, list):
        errors.append("free_lines must be a list")
        source_free = []
    for index, source in enumerate(source_free, 1):
        line = deepcopy(source or {})
        code = _text(line.get("product_code")).lower()
        product = SOTEPHWAR_PRODUCTS.get(code)
        if not product:
            errors.append(f"free line {index} product_code is invalid")
        quantity = _decimal(line.get("quantity"), f"free line {index} quantity", errors, positive=True)
        if quantity != quantity.to_integral_value():
            errors.append(f"free line {index} quantity must be a positive whole number")
        if code in seen_free:
            errors.append(f"free line {index} duplicates product_code {code}")
        seen_free.add(code)
        free_lines.append({
            "product_code": code, "description": product["item"] if product else "",
            "unit": "bottle", "quantity": quantity, "note": _text(line.get("note")),
        })
    if errors:
        raise VoucherValidationError(errors)
    voucher["lines"] = lines
    voucher["paid_lines"] = deepcopy(lines)
    voucher["free_lines"] = free_lines
    voucher["status"] = "validated"
    return voucher


def preview_sotephwar(draft):
    voucher = validate_sotephwar(draft)
    gross = sum((line["amount"] for line in voucher["lines"]), Decimal("0.00"))
    errors = []
    voucher["total_amount"] = _adjustments(voucher, gross, errors)
    voucher["amount_received"] = _decimal(voucher.get("amount_received", 0), "amount_received", errors)
    if voucher["amount_received"] < 0:
        errors.append("amount_received cannot be negative")
    if voucher["amount_received"] > voucher["net_amount"]:
        errors.append("amount_received cannot exceed net_amount")
    if errors:
        raise VoucherValidationError(errors)
    voucher["outstanding_balance"] = voucher["total_amount"] - voucher["amount_received"]
    voucher["payment_status"] = (
        "Paid" if voucher["outstanding_balance"] == 0 else
        "Partial" if voucher["amount_received"] > 0 else "Outstanding"
    )
    voucher["delivery_sections"] = [{
        "delivery_date": voucher["voucher_date"],
        "items": deepcopy(voucher["lines"]),
        "subtotal": voucher["gross_amount"],
    }]
    voucher["status"] = "previewed"
    voucher["print_title"] = "SOTEPHWAR SALES INVOICE"
    return voucher


def _allocate_whole_mmk(total, weights, capacities=None):
    """Allocate an integral MMK total proportionally, exactly and without exceeding capacity."""
    total = Decimal(total).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    capacities = [Decimal(value) for value in (capacities or weights)]
    result = []
    remaining = total
    remaining_weight = sum((Decimal(value) for value in weights), Decimal("0"))
    for index, weight in enumerate(weights):
        weight = Decimal(weight)
        if index == len(weights) - 1:
            share = remaining
        elif remaining_weight <= 0:
            share = Decimal("0")
        else:
            share = (remaining * weight / remaining_weight).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        share = max(Decimal("0"), min(share, capacities[index], remaining))
        result.append(share)
        remaining -= share
        remaining_weight -= weight
    if remaining:
        for index in range(len(result) - 1, -1, -1):
            available = capacities[index] - result[index]
            addition = min(available, remaining)
            result[index] += addition
            remaining -= addition
            if not remaining:
                break
    if remaining:
        raise VoucherValidationError(["adjustments could not be allocated across paid product lines"])
    return result


def sotephwar_transaction_rows(draft):
    """Allocate one voucher payment across SotePhwar product rows exactly."""
    voucher = preview_sotephwar(draft)
    gross_total = voucher["gross_amount"]
    grand_total = voucher["net_amount"]
    received = voucher["amount_received"]
    allocated = Decimal("0.00")
    gross_lines = [line["amount"] for line in voucher["lines"]]
    discounts = _allocate_whole_mmk(voucher["discount_amount"], gross_lines, gross_lines)
    post_discount = [gross - discount for gross, discount in zip(gross_lines, discounts)]
    cashbacks = _allocate_whole_mmk(voucher["cashback_amount"], gross_lines, post_discount)
    rows = []
    for index, line in enumerate(voucher["lines"]):
        final = index == len(voucher["lines"]) - 1
        line_discount = discounts[index]
        line_cashback = cashbacks[index]
        line_net = line["amount"] - line_discount - line_cashback
        if final:
            line_received = received - allocated
        elif grand_total == 0:
            line_received = Decimal("0.00")
        else:
            line_received = (received * line_net / grand_total).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            allocated += line_received
        outstanding = line_net - line_received
        status = "Paid" if outstanding == 0 else "Partial" if line_received > 0 else "Outstanding"
        rows.append({
            "Invoice_Number": voucher["voucher_number"],
            "Invoice_Date": voucher["voucher_date"],
            "Customer_Name": voucher["customer_name"],
            "Item": line["item"],
            "Quantity": int(line["quantity"]),
            "Total_Amount": line_net,
            "Total_Received": line_received,
            "Outstanding_Balance": outstanding,
            "Payment_Status": status,
            "Note": line["note"] or voucher["note"],
            "product_code": line["product_code"],
            "unit_price": line["unit_price"],
            "gross_amount": line["amount"], "allocated_discount": line_discount,
            "allocated_cashback": line_cashback,
        })
    return rows
