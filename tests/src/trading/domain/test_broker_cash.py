"""Tests for trading.domain.broker_cash."""

from __future__ import annotations

from decimal import Decimal

import pytest

from trading.domain.broker_cash import BROKER_CASH_TOLERANCE, broker_cash_shortfall


@pytest.mark.parametrize(
    ("book_cash", "broker_cash", "expected"),
    [
        (Decimal("80000.00"), 70000.0, Decimal("9999.00")),
        (Decimal("70000.00"), 70000.0, Decimal(0)),
        (Decimal("60000.00"), 70000.0, Decimal(0)),
        (Decimal("70000.00") + BROKER_CASH_TOLERANCE, 70000.0, Decimal(0)),
        (Decimal("70001.01"), 70000.0, Decimal("0.01")),
        (Decimal("10.00"), 0.0, Decimal("9.00")),
    ],
)
def test_shortfall_is_the_excess_beyond_the_tolerance(
    book_cash: Decimal, broker_cash: float, expected: Decimal
) -> None:
    assert broker_cash_shortfall(book_cash, broker_cash) == expected
