"""Shared presentation helpers for evaluation evidence.

The reporting evaluation summary and the promotion status view render the same
backtest-freshness decision (measurable? stale or fresh?). This module owns that
shared reduction; each caller formats the parts for its own surface.
"""

from __future__ import annotations

from trading.models.evaluation import BacktestFreshness


def backtest_freshness_display_parts(freshness: BacktestFreshness | None) -> tuple[float, str] | None:
    """Return ``(age_days, "stale"|"fresh")`` when freshness is measurable, else ``None``."""
    if freshness is None or not freshness.available or freshness.age_days is None:
        return None
    return freshness.age_days, "stale" if freshness.is_stale else "fresh"


__all__ = ["backtest_freshness_display_parts"]
