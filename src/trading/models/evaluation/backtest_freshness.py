from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BacktestFreshness:
    """Advisory staleness of a strategy's newest backtest evidence (P12).

    ``age_days`` is the fractional age of the backtest run against the
    evaluation's generation time; ``is_stale`` compares it to
    ``stale_threshold_days``. ``available`` is False when there is no backtest
    run to measure. Advisory only — never affects confidence or decisions.
    """

    available: bool = False
    age_days: float | None = None
    stale_threshold_days: int = 0
    is_stale: bool = False
