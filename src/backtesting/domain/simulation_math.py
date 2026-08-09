"""Fill arithmetic for one simulated account.

``update_on_buy`` and ``update_on_sell`` mutate the ``positions`` and ``avg_cost``
dicts they are handed and return only the values that cannot be updated in place
(cash, and realized P&L on a sell). Callers own those dicts and see the change.

Valuation lives in ``trading.domain.portfolio_math``, which the live runtime
shares.
"""

from __future__ import annotations


def update_on_buy(
    ticker: str,
    qty: float,
    price: float,
    fee: float,
    positions: dict[str, float],
    avg_cost: dict[str, float],
    cash: float,
) -> float:
    """Apply a buy fill, returning the new cash balance.

    Raises the position and re-averages its cost in place. The fee is capitalized
    into the cost basis, so ``avg_cost`` is what the shares actually cost to acquire.
    """
    old_qty = positions[ticker]
    new_qty = old_qty + qty
    if new_qty <= 0:
        raise ValueError(
            f"update_on_buy: resulting position for {ticker!r} is non-positive ({new_qty}). qty must be positive."
        )
    old_value = old_qty * avg_cost[ticker]
    trade_value = (qty * price) + fee
    avg_cost[ticker] = (old_value + trade_value) / new_qty
    positions[ticker] = new_qty
    return cash - trade_value


def update_on_sell(
    ticker: str,
    qty: float,
    price: float,
    fee: float,
    positions: dict[str, float],
    avg_cost: dict[str, float],
    cash: float,
    realized_pnl: float,
) -> tuple[float, float]:
    """Apply a sell fill, returning the new ``(cash, realized_pnl)`` pair.

    Reduces the position in place and clears its average cost once the holding is
    flat. The fee is charged against realized P&L as well as netted out of proceeds,
    so a round trip is costed on both legs.
    """
    proceeds = (qty * price) - fee
    cash += proceeds
    realized_pnl += ((price - avg_cost[ticker]) * qty) - fee
    positions[ticker] -= qty
    if positions[ticker] <= 0:
        positions[ticker] = 0.0
        avg_cost[ticker] = 0.0
    return cash, realized_pnl
