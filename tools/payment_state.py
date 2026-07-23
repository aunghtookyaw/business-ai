"""Read-only current payment state built from canonical Formula Engine logic."""

from tools import formula_engine


def current_voucher_payment_state(sector, voucher_number, invoice_date=None, customer=None):
    """Return current state from voucher totals plus append-only Payment_Receive rows."""
    voucher = formula_engine._payment_voucher_lookup(
        sector, voucher_number, invoice_date=invoice_date, customer=customer,
    )
    if not voucher:
        raise LookupError("Voucher not found")
    total = int(voucher.get("invoice_amount") or 0)
    received = formula_engine._payment_receive_total(
        sector, voucher_number, invoice_date=invoice_date, customer=customer,
    )
    # Preserve imported/pre-existing paid amounts when they exceed payment history.
    received = max(int(received or 0), int(voucher.get("current_received") or 0))
    outstanding, status = formula_engine._payment_balance_status(total, received)
    if outstanding < 0:
        raise ValueError("Outstanding_Balance cannot be negative.")
    latest = formula_engine._fetch_one(
        f'''
        SELECT MAX("Receive_Date") AS latest_payment_date
        FROM {formula_engine._payment_receive_table_ref()}
        WHERE "Sector" = %(sector)s
          AND "Voucher_Number" = %(voucher_number)s
          AND ("Invoice_Date" = %(invoice_date)s OR "Invoice_Date" IS NULL)
          AND (COALESCE("Customer", '') = %(customer)s OR COALESCE("Customer", '') = '')
        ''',
        {
            "sector": sector,
            "voucher_number": str(voucher_number),
            "invoice_date": invoice_date or voucher.get("invoice_date"),
            "customer": customer or voucher.get("customer") or "",
        },
    )
    latest_date = (latest or {}).get("latest_payment_date")
    return {
        "invoice_amount": total,
        "current_received": received,
        "current_outstanding": outstanding,
        "current_payment_status": status,
        "latest_payment_date": latest_date.isoformat() if hasattr(latest_date, "isoformat") else latest_date,
    }
