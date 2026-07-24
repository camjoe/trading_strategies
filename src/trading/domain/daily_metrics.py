"""Pure derivation of a book's per-day performance metrics.

Computes the `daily_metrics` columns that are honestly derivable from stored
daily activity — a book's equity snapshots plus its filled orders for the day.

Four contract columns are deliberately left ``None`` because the inputs to
compute them honestly are not stored at this grain (see
``docs/reference/performance-and-risk-tables.md``):

- ``drawdown_pct`` — needs intraday equity; only daily snapshots exist.
- ``hit_rate`` / ``expectancy`` — need per-trade realized P&L; fills store only
  qty/price/commission, and realized P&L is stored per-book (cumulative), never
  per trade.
- ``risk_adjusted_score`` — Sharpe/Sortino need a return *series*; one day cannot
  produce one (a trailing-window writer could, later).
"""

from __future__ import annotations

from dataclasses import dataclass

BASIS_POINTS = 10_000.0


@dataclass(frozen=True, slots=True)
class DailyTrade:
    """One filled order contributing to a day's activity."""

    side: str  # "buy" | "sell"
    filled_qty: float
    avg_fill_price: float
    requested_price: float | None
    commission: float


@dataclass(frozen=True, slots=True)
class DailyBookMetrics:
    trade_count: int
    fees_total: float
    return_pct: float | None
    turnover_pct: float | None
    slippage_bps: float | None
    # Not derivable from stored per-day data — see module docstring.
    drawdown_pct: float | None = None
    hit_rate: float | None = None
    expectancy: float | None = None
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

    return DailyBookMetrics(
        trade_count=len(trades),
        fees_total=fees_total,
        return_pct=return_pct,
        turnover_pct=turnover_pct,
        slippage_bps=_average_slippage_bps(trades),
    )


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
