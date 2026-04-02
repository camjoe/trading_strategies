from __future__ import annotations


def compute_market_value(positions: dict[str, float], prices: dict[str, float]) -> float:
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
    old_qty = positions[ticker]
    new_qty = old_qty + qty
    if new_qty <= 0:
        raise ValueError(
            f"update_on_buy: resulting position for {ticker!r} is non-positive ({new_qty}). "
            "qty must be positive."
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
    total = 0.0
    for ticker, qty in positions.items():
        if qty <= 0:
            continue
        total += (marks[ticker] - avg_cost[ticker]) * qty
    return total
