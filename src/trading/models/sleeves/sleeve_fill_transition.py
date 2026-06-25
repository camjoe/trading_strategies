from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SleeveFillTransition:
    symbol: str
    side: str
    qty: float
    fill_price: float
    commission: float
    requested_price: float | None
    cash_delta: float
    realized_pnl_delta: float
    slippage_amount: float
    ending_qty: float
    ending_avg_cost: float
    ending_cash: float
    ending_realized_pnl: float
    ending_market_value: float
    ending_unrealized_pnl: float
    ending_equity: float
