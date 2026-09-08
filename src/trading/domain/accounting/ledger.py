"""Pure per-fill ledger deltas shared by account replay and book fills — no I/O."""

from __future__ import annotations

from typing import NamedTuple


class BuyDelta(NamedTuple):
    ending_qty: float
    ending_avg_cost: float
    cash_delta: float


class SellDelta(NamedTuple):
    ending_qty: float
    cash_delta: float
    realized_delta: float


def buy_position_delta(
    *, position_qty: float, position_avg_cost: float, qty: float, price: float, fee: float
) -> BuyDelta:
    """The position, average cost, and cash change from one buy fill.

    The fee is capitalized into the cost basis, so ``ending_avg_cost`` is what the
    shares actually cost to acquire. The caller must reject a non-positive
    ``position_qty + qty`` first — this divides by the ending quantity.
    """
    trade_value = qty * price + fee
    ending_qty = position_qty + qty
    ending_avg_cost = (position_qty * position_avg_cost + trade_value) / ending_qty
    return BuyDelta(ending_qty=ending_qty, ending_avg_cost=ending_avg_cost, cash_delta=-trade_value)


def sell_position_delta(
    *, position_qty: float, position_avg_cost: float, qty: float, price: float, fee: float
) -> SellDelta:
    """The position, cash, and realized-P&L change from one sell fill.

    The fee is charged against realized P&L and netted out of proceeds, so a round
    trip is costed on both legs. A sell does not re-average cost; the caller decides
    whether to keep or drop the average on a full close.
    """
    proceeds = qty * price - fee
    ending_qty = position_qty - qty
    realized_delta = (price - position_avg_cost) * qty - fee
    return SellDelta(ending_qty=ending_qty, cash_delta=proceeds, realized_delta=realized_delta)
