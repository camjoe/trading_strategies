"""Compounded out-of-sample aggregation for a walk-forward optimization run.

Pure domain math: the service layer reads each window's OOS equity marks and hands
the resulting segments here.
"""

from __future__ import annotations

from datetime import date, timedelta

from backtesting.domain.metrics import PERCENT_SCALE
from backtesting.models.optimizer import (
    CompoundedOOSPoint,
    CompoundedOOSSeries,
    OOSReturnSegment,
)


def compound_oos_returns(segments: list[OOSReturnSegment]) -> CompoundedOOSSeries:
    """Compound per-window OOS returns into a single chronological series.

    Segments must already be in chronological order and must not overlap. A segment
    whose interval does not abut the previous one is flagged ``gap_before``.
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
                test_start=segment.test_start,
                test_end=segment.test_end,
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
