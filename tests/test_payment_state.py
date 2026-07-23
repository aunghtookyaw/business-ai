from datetime import date
from unittest.mock import patch

import pytest

from tools.payment_state import current_voucher_payment_state


@pytest.mark.parametrize(
    "payment_total,source_received,expected_received,expected_outstanding,expected_status",
    [
        (0, 0, 0, 1880000, "Outstanding"),
        (880000, 0, 880000, 1000000, "Partial"),
        (1880000, 0, 1880000, 0, "Paid"),
        (1000000, 880000, 1000000, 880000, "Partial"),
    ],
)
def test_current_payment_states(payment_total, source_received, expected_received, expected_outstanding, expected_status):
    with (
        patch("tools.payment_state.formula_engine._payment_voucher_lookup", return_value={
            "invoice_amount": 1880000, "current_received": source_received,
            "invoice_date": date(2026, 7, 1), "customer": "Customer",
        }),
        patch("tools.payment_state.formula_engine._payment_receive_total", return_value=payment_total),
        patch("tools.payment_state.formula_engine._fetch_one", return_value={"latest_payment_date": date(2026, 7, 20)}),
    ):
        result = current_voucher_payment_state("Farm", "FV-1", date(2026, 7, 1), "Customer")
    assert result["current_received"] == expected_received
    assert result["current_outstanding"] == expected_outstanding
    assert result["current_payment_status"] == expected_status
    assert result["latest_payment_date"] == "2026-07-20"


def test_multiple_append_only_payments_use_canonical_aggregate():
    with (
        patch("tools.payment_state.formula_engine._payment_voucher_lookup", return_value={
            "invoice_amount": 1880000, "current_received": 0,
        }),
        patch("tools.payment_state.formula_engine._payment_receive_total", return_value=880000 + 400000 + 600000) as total,
        patch("tools.payment_state.formula_engine._fetch_one", return_value={"latest_payment_date": None}),
    ):
        result = current_voucher_payment_state("Farm", "FV-1")
    total.assert_called_once()
    assert result["current_received"] == 1880000
    assert result["current_outstanding"] == 0
    assert result["current_payment_status"] == "Paid"


def test_historical_voucher_without_payment_rows_preserves_source_received():
    with (
        patch("tools.payment_state.formula_engine._payment_voucher_lookup", return_value={
            "invoice_amount": 1880000, "current_received": 880000,
        }),
        patch("tools.payment_state.formula_engine._payment_receive_total", return_value=0),
        patch("tools.payment_state.formula_engine._fetch_one", return_value={"latest_payment_date": None}),
    ):
        result = current_voucher_payment_state("Farm", "FV-OLD")
    assert result["current_received"] == 880000
    assert result["current_outstanding"] == 1000000
    assert result["current_payment_status"] == "Partial"
