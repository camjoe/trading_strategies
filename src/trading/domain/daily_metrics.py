"""Pure derivation of a book's per-day performance metrics.

Computes the `daily_metrics` columns that are honestly derivable from stored
daily activity — a book's equity snapshots plus its filled orders for the day.

``hit_rate`` and ``expectancy`` are derived from each closing order's realized
P&L (``orders.realized_pnl_delta``, populated for sells). ``risk_adjusted_score``
is a trailing annualized Sharpe ratio over the book's recent daily returns: one
day cannot produce a return series, but the persisted ``daily_metrics.return_pct``
history is one, so the writer feeds the prior sessions' returns in as
``prior_returns``. See ``docs/reference/performance-and-risk-tables.md``.

One contract column is still left ``None`` because its input is not stored at
this grain: ``drawdown_pct`` needs intraday equity; only daily snapshots exist.
"""

from __future__ import annotations

from dataclasses import dataclass

from common.constants import ANNUALIZATION_FACTOR

BASIS_POINTS = 10_000.0

# Trailing window (in scored sessions, including the current day) the daily
# risk-adjusted score is computed over — roughly one trading month.
RISK_ADJUSTED_WINDOW_SESSIONS = 20

# Minimum scored sessions required before a trailing risk-adjusted score is
# reported. Below this the sample is too small for the ratio to mean anything,
# so the score stays ``None`` rather than publishing noise.
RISK_ADJUSTED_MIN_SESSIONS = 10


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
    risk_adjusted_score: float | None
    # Not derivable from stored per-day data (needs intraday equity) — see module docstring.
    drawdown_pct: float | None = None


def compute_daily_book_metrics(
    *,
    prev_equity: float | None,
    end_equity: float | None,
    trades: list[DailyTrade],
    prior_returns: list[float] | None = None,
) -> DailyBookMetrics:
    """Derive one book's metrics for a day from its equity boundaries and fills.

    ``prev_equity`` is the book's equity at the previous snapshot (None on the
    book's first day → no return). ``end_equity`` is the book's equity at the end
    of the day. ``prior_returns`` are the book's earlier daily ``return_pct``
    values (most-recent-first) that combine with the current day to form the
    trailing risk-adjusted score's window; omit them and the score stays ``None``.
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
        risk_adjusted_score=_trailing_risk_adjusted_score(prior_returns or [], return_pct),
    )


def _trailing_risk_adjusted_score(prior_returns: list[float], today_return: float | None) -> float | None:
    """Annualized Sharpe ratio over the book's most recent daily returns.

    Combines ``today_return`` (most recent) with ``prior_returns`` (already
    most-recent-first), caps the series to ``RISK_ADJUSTED_WINDOW_SESSIONS``, and
    returns ``mean / population_std * ANNUALIZATION_FACTOR`` — the same convention
    as ``backtesting/domain/metrics.py::sharpe_ratio`` (risk-free rate 0). Returns
    ``None`` when there are fewer than ``RISK_ADJUSTED_MIN_SESSIONS`` returns or
    the returns have no dispersion (a zero-volatility Sharpe is undefined).
    """
    series = ([today_return] if today_return is not None else []) + prior_returns
    window = series[:RISK_ADJUSTED_WINDOW_SESSIONS]
    if len(window) < RISK_ADJUSTED_MIN_SESSIONS:
        return None
    mean = sum(window) / len(window)
    variance = sum((value - mean) ** 2 for value in window) / len(window)
    std = variance**0.5
    if std <= 0:
        return None
    return mean / std * ANNUALIZATION_FACTOR


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
