"""Pure per-fill ledger deltas shared by account replay and book fills — no I/O."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Generic, TypeVar

# One implementation serves two callers: the float backtest loop and the Decimal
# live accounting path (ADR 020). The constrained type variable keeps each call
# single-typed — a caller passes all float or all Decimal and gets that type back —
# so mypy rejects a float/Decimal mix, which Python would raise on at runtime.
Number = TypeVar("Number", float, Decimal)


@dataclass(frozen=True, slots=True)
class BuyDelta(Generic[Number]):
    ending_qty: Number
    ending_avg_cost: Number
    cash_delta: Number


@dataclass(frozen=True, slots=True)
class SellDelta(Generic[Number]):
    ending_qty: Number
    cash_delta: Number
    realized_delta: Number


def buy_position_delta(
    *, position_qty: Number, position_avg_cost: Number, qty: Number, price: Number, fee: Number
) -> BuyDelta[Number]:
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
    *, position_qty: Number, position_avg_cost: Number, qty: Number, price: Number, fee: Number
) -> SellDelta[Number]:
    """The position, cash, and realized-P&L change from one sell fill.

    The fee is charged against realized P&L and netted out of proceeds, so a round
    trip is costed on both legs. A sell does not re-average cost; the caller decides
    whether to keep or drop the average on a full close.
    """
    proceeds = qty * price - fee
    ending_qty = position_qty - qty
    realized_delta = (price - position_avg_cost) * qty - fee
    return SellDelta(ending_qty=ending_qty, cash_delta=proceeds, realized_delta=realized_delta)
