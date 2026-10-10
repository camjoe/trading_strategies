"""Pure arithmetic turning a broker's cumulative fill report into the fill still to post.

Some brokers state only an order's cumulative filled size, average price and commission,
with no individual executions. The book needs the part not yet recorded, priced at what
that part cost, so posting the same report twice posts nothing and a partial fill followed
by the rest posts each part once at its own price.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

_ZERO = Decimal("0")


class UnpostableFillError(ValueError):
    """The report cannot be turned into a fill that is safe to post; the message says why."""


@dataclass(frozen=True, slots=True)
class IncrementalFill:
    qty: Decimal
    price: Decimal
    commission: Decimal


def incremental_fill(
    *,
    reported_qty: Decimal,
    reported_avg_price: Decimal | None,
    reported_commission: Decimal,
    recorded_qty: Decimal,
    recorded_notional: Decimal,
    recorded_commission: Decimal,
) -> IncrementalFill | None:
    """The fill beyond what is recorded, or None when the report adds nothing.

    The price is whatever the new shares cost given the reported cumulative average and
    the notional already recorded. Raises ``UnpostableFillError`` when the report is less
    than what is recorded, carries no price for new shares, or implies a non-positive price.
    """
    new_qty = reported_qty - recorded_qty
    if new_qty < _ZERO:
        raise UnpostableFillError(f"broker reports {reported_qty} filled, less than the {recorded_qty} recorded")
    if new_qty == _ZERO:
        return None
    if reported_avg_price is None:
        raise UnpostableFillError(f"broker reports {reported_qty} filled with no average price")
    price = (reported_qty * reported_avg_price - recorded_notional) / new_qty
    if price <= _ZERO:
        raise UnpostableFillError(
            f"average price {reported_avg_price} over {reported_qty} shares implies a price of {price} "
            f"for the {new_qty} not yet recorded"
        )
    return IncrementalFill(qty=new_qty, price=price, commission=max(reported_commission - recorded_commission, _ZERO))
