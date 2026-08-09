"""Ledger arithmetic for one simulated account: market value, fills, and P&L.

``update_on_buy`` and ``update_on_sell`` mutate the ``positions`` and ``avg_cost``
dicts they are handed and return only the values that cannot be updated in place
(cash, and realized P&L on a sell). Callers own those dicts and see the change.

The two valuation helpers differ on missing data by design: ``compute_market_value``
prices what it can and skips the rest, while ``compute_unrealized_pnl`` raises,
because an equity mark with a silently omitted holding is a wrong number rather
than a partial one.
"""

from __future__ import annotations


def compute_market_value(positions: dict[str, float], prices: dict[str, float]) -> float:
    """Total value of *positions* at *prices*, skipping tickers with no price."""
    total = 0.0
    for ticker, qty in positions.items():
        px = prices.get(ticker)
        if px is None:
            continue
        total += qty * px
    return total


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


def compute_unrealized_pnl(
    positions: dict[str, float],
    avg_cost: dict[str, float],
    marks: dict[str, float],
) -> float:
    """Open P&L across held positions. Raises ``KeyError`` if a holding has no mark."""
    total = 0.0
    for ticker, qty in positions.items():
        if qty <= 0:
            continue
        total += (marks[ticker] - avg_cost[ticker]) * qty
    return total
