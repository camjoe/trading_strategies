"""Pure derivation of a book's per-day performance metrics.

Computes the `daily_metrics` columns that are honestly derivable from stored
daily activity — a book's equity snapshots plus its filled orders for the day.

``hit_rate`` and ``expectancy`` are derived from each closing order's realized
P&L (``orders.realized_pnl_delta``, populated for sells). Two contract columns
are still left ``None`` because their inputs are not stored at this grain (see
``docs/reference/performance-and-risk-tables.md``):

- ``drawdown_pct`` — needs intraday equity; only daily snapshots exist.
- ``risk_adjusted_score`` — Sharpe/Sortino need a return *series*; one day cannot
  produce one (a trailing-window writer could, later).
"""

from __future__ import annotations

from dataclasses import dataclass

BASIS_POINTS = 10_000.0


@dataclass(frozen=True, slots=True)
class DailyTrade:
    """One filled order contributing to a day's activity.

    ``realized_pnl_delta`` is the order's realized P&L, present only for closing
    orders (sells); ``None`` marks an opening order that realized nothing.
    """

    side: str  # "buy" | "sell"
    filled_qty: float
    avg_fill_price: float
    requested_price: float | None
    commission: float
    realized_pnl_delta: float | None = None


@dataclass(frozen=True, slots=True)
class DailyBookMetrics:
    trade_count: int
    fees_total: float
    return_pct: float | None
    turnover_pct: float | None
    slippage_bps: float | None
    hit_rate: float | None
    expectancy: float | None
    # Not derivable from stored per-day data — see module docstring.
    drawdown_pct: float | None = None
    risk_adjusted_score: float | None = None


def compute_daily_book_metrics(
    *,
    prev_equity: float | None,
    end_equity: float | None,
    trades: list[DailyTrade],
) -> DailyBookMetrics:
    """Derive one book's metrics for a day from its equity boundaries and fills.

    ``prev_equity`` is the book's equity at the previous snapshot (None on the
    book's first day → no return). ``end_equity`` is the book's equity at the end
    of the day.
    """
    fees_total = round(sum(trade.commission for trade in trades), 6)
    notional = sum(abs(trade.filled_qty) * trade.avg_fill_price for trade in trades)

    return_pct: float | None = None
    if prev_equity is not None and prev_equity != 0 and end_equity is not None:
        return_pct = (end_equity / prev_equity - 1.0) * 100.0

    turnover_pct: float | None = None
    if trades and end_equity is not None and end_equity != 0:
        turnover_pct = notional / end_equity * 100.0

    hit_rate, expectancy = _closing_trade_stats(trades)

    return DailyBookMetrics(
        trade_count=len(trades),
        fees_total=fees_total,
        return_pct=return_pct,
        turnover_pct=turnover_pct,
        slippage_bps=_average_slippage_bps(trades),
        hit_rate=hit_rate,
        expectancy=expectancy,
    )


def _closing_trade_stats(trades: list[DailyTrade]) -> tuple[float | None, float | None]:
    """Win rate and average realized P&L over the day's closing trades.

    A closing trade is one that realized P&L (``realized_pnl_delta`` is not None —
    sells). Both are ``None`` on a day with no closes, so an opening-only day never
    reads as 0% hit rate.
    """
    realized = [trade.realized_pnl_delta for trade in trades if trade.realized_pnl_delta is not None]
    if not realized:
        return None, None
    hit_rate = sum(1 for pnl in realized if pnl > 0) / len(realized)
    expectancy = sum(realized) / len(realized)
    return hit_rate, expectancy


def _average_slippage_bps(trades: list[DailyTrade]) -> float | None:
    """Average execution slippage across priced fills, in basis points.

    Cost-signed: positive means worse-than-requested execution (paid more on a
    buy, received less on a sell). Fills with no requested price are excluded;
    ``None`` when no fill carries a comparable price.
    """
    priced = [trade for trade in trades if trade.requested_price not in (None, 0)]
    if not priced:
        return None
    total_fraction = 0.0
    for trade in priced:
        requested = trade.requested_price
        assert requested is not None  # narrowed by the filter above
        if trade.side == "buy":
            total_fraction += (trade.avg_fill_price - requested) / requested
        else:
            total_fraction += (requested - trade.avg_fill_price) / requested
    return total_fraction / len(priced) * BASIS_POINTS
