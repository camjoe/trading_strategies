from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SleeveTradeIntent:
    account_id: int
    # The trading book this intent belongs to — the primary key of the flow.
    book_id: int
    strategy_name: str
    param_set_id: int | None
    side: str
    symbol: str
    qty: int
    requested_price: float
    forced_sell: str | None
    delta_est: float | None
    iv_est: float | None
