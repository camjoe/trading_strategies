"""Whether the cash the books hold is cash the broker can actually spend."""

from __future__ import annotations

from decimal import Decimal

# Cash the books may hold above the broker's figure before it counts as a shortfall: absorbs
# cent rounding between the ledger and the broker's cash balance.
BROKER_CASH_TOLERANCE = Decimal("1.00")


def broker_cash_shortfall(book_cash: Decimal, broker_cash: float) -> Decimal:
    """How far the books' cash exceeds the broker's, beyond the tolerance; zero when it does not."""
    excess = book_cash - Decimal(str(broker_cash)) - BROKER_CASH_TOLERANCE
    return max(excess, Decimal(0))
