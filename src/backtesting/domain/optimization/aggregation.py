"""Compounded out-of-sample aggregation for a walk-forward optimization run.

Beyond the per-window distribution, this assembles a single chronological OOS
series across an experiment's non-overlapping windows. Each OOS window runs on an
independently reset account, so window returns are **compounded** (geometrically
linked), never summed on equity. A window whose OOS interval does not immediately
follow the previous one — a ``step_months`` longer than ``test_months`` — is
flagged so the discontinuity is visible rather than silently smoothed over.

Pure domain math: no I/O. The service layer reads each window's OOS equity marks
and hands the resulting segments here.
"""

from __future__ import annotations

from datetime import date, timedelta

from backtesting.domain.metrics import PERCENT_SCALE
from backtesting.models.optimizer import (
    CompoundedOOSPoint,
    CompoundedOOSSeries,
    OOSReturnSegment,
)


def period_return_pct(*, first_equity: float, last_equity: float) -> float:
    """Total return over an interval from its first and last equity marks (percent).

    Matches the standalone backtest report's total-return definition, so a compounded
    segment measures the same thing the optimizer's per-window OOS return did.
    """
    return ((last_equity / first_equity) - 1.0) * PERCENT_SCALE


def compound_oos_returns(segments: list[OOSReturnSegment]) -> CompoundedOOSSeries:
    """Compound non-overlapping per-window OOS returns into a chronological series.

    Returns are multiplied (compounded), never summed on equity, because each OOS
    window is an independently reset account. A window whose interval does not abut
    the previous one is flagged ``gap_before`` so the time gap is disclosed. The
    segments are assumed already in chronological order (the repository returns
    windows by ``window_index``).
    """
    points: list[CompoundedOOSPoint] = []
    growth = 1.0
    previous_end: date | None = None
    for segment in segments:
        growth *= 1.0 + segment.return_pct / PERCENT_SCALE
        gap_before = previous_end is not None and segment.test_start > previous_end + timedelta(days=1)
        points.append(
            CompoundedOOSPoint(
                window_index=segment.window_index,
                test_start=segment.test_start.isoformat(),
                test_end=segment.test_end.isoformat(),
                period_return_pct=segment.return_pct,
                cumulative_return_pct=(growth - 1.0) * PERCENT_SCALE,
                gap_before=gap_before,
            )
        )
        previous_end = segment.test_end
    return CompoundedOOSSeries(
        points=points,
        compounded_return_pct=(growth - 1.0) * PERCENT_SCALE,
        has_gaps=any(point.gap_before for point in points),
    )
