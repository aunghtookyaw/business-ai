"""Generate the non-production Farm Voucher PDF used for visual verification."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tools import voucher_engine
from tools.farm_voucher_pdf import write_farm_voucher_pdf


OUTPUT = ROOT / "output/pdf/farm_voucher_preview_verified.pdf"


def main():
    draft = {
        "sector": "farm",
        "voucher_number": "900777",
        "voucher_date": "2026-07-16",
        "customer_id": 999999,
        "customer_name": "Farm Buyer",
        "customer_snapshot": {
            "customer_name": "Farm Buyer",
            "phone_number": "091234567",
            "town": "Heho",
            "contact_address": "No. 10 Farm Road, Heho",
            "customer_group": "Farm",
            "payment_terms_days": 30,
        },
        "payment_method": "Bank transfer",
        "amount_received": "1000",
        "note": "Design verification sample - not submitted",
        "delivery_sections": [
            {"delivery_date": "2026-07-10", "items": [
                {"crop_id": 1, "crop_name": "Beetroot", "quantity": 2, "unit": "kg", "unit_price": 1500},
                {"crop_id": 2, "crop_name": "Cherry Tomato", "quantity": 1.5, "unit": "kg", "unit_price": 2400},
            ]},
            {"delivery_date": "2026-07-12", "items": [
                {"custom_description": "Seasonal Gift Basket", "quantity": 3, "unit": "set", "unit_price": 2000},
            ]},
        ],
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    write_farm_voucher_pdf(voucher_engine.preview(draft), OUTPUT)
    print(OUTPUT)


if __name__ == "__main__":
    main()
