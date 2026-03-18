from __future__ import annotations

from datetime import date

import pytest

from trading.features.backtesting.backtest import build_walk_forward_windows


@pytest.mark.parametrize("test_months", [1, 2, 3])
@pytest.mark.parametrize("step_months", [1, 2, 3])
@pytest.mark.parametrize(
    ("start_date", "end_date"),
    [
        (date(2026, 1, 1), date(2026, 1, 31)),
        (date(2026, 1, 15), date(2026, 4, 10)),
        (date(2026, 2, 28), date(2026, 5, 2)),
        (date(2026, 3, 31), date(2026, 8, 1)),
    ],
)
def test_walk_forward_windows_stay_within_range_and_monotonic(
    start_date: date,
    end_date: date,
    test_months: int,
    step_months: int,
) -> None:
    windows = build_walk_forward_windows(
        start_date=start_date,
        end_date=end_date,
        test_months=test_months,
        step_months=step_months,
    )

    prev_start: date | None = None
    for window_start, window_end in windows:
        assert start_date <= window_start <= end_date
        assert start_date <= window_end <= end_date
        assert window_start < window_end
        if prev_start is not None:
            assert window_start >= prev_start
        prev_start = window_start


@pytest.mark.parametrize(
    ("start_date", "end_date", "test_months", "step_months"),
    [
        (date(2026, 1, 31), date(2026, 2, 1), 1, 1),
        (date(2026, 2, 28), date(2026, 3, 1), 1, 1),
        (date(2026, 6, 30), date(2026, 7, 1), 1, 2),
    ],
)
def test_walk_forward_windows_can_be_empty_for_tiny_ranges(
    start_date: date,
    end_date: date,
    test_months: int,
    step_months: int,
) -> None:
    windows = build_walk_forward_windows(
        start_date=start_date,
        end_date=end_date,
        test_months=test_months,
        step_months=step_months,
    )
    assert windows == []
