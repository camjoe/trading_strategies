"""Backtest freshness assessment (advisory-only).

Pure policy over backtest-run timestamps: how many days old the newest backtest
is, and whether that exceeds the advisory staleness threshold. Never affects
confidence or decisions — it only produces a diagnostic an operator can read.
"""

from __future__ import annotations

from common.time import days_between
from trading.models.evaluation.backtest_freshness import BacktestFreshness

# The daily backtest_refresh job re-runs backtests once per day, so backtest
# evidence older than a few missed refreshes is worth flagging. Three days
# tolerates a weekend or a short refresh outage before the advisory trips.
DEFAULT_BACKTEST_STALE_THRESHOLD_DAYS = 3


def assess_backtest_freshness(
    *,
    backtest_created_at: str | None,
    reference_iso: str,
    threshold_days: int = DEFAULT_BACKTEST_STALE_THRESHOLD_DAYS,
) -> BacktestFreshness:
    """Assess how stale the newest backtest is as of ``reference_iso``.

    ``backtest_created_at`` is the run's recalculation time (freshness cadence);
    ``reference_iso`` is the evaluation "now" (its ``generated_at``). Returns an
    unavailable result when there is no backtest run to measure.
    """
    if backtest_created_at is None:
        return BacktestFreshness(available=False, stale_threshold_days=threshold_days)
    age_days = days_between(backtest_created_at, reference_iso)
    return BacktestFreshness(
        available=True,
        age_days=age_days,
        stale_threshold_days=threshold_days,
        is_stale=age_days > threshold_days,
    )
