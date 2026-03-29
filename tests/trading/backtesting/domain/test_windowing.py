from __future__ import annotations

from datetime import date

import pytest

from trading.backtesting.domain.windowing import add_months, build_walk_forward_windows


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


def test_build_walk_forward_windows_rejects_non_positive_lengths() -> None:
    with pytest.raises(ValueError, match="test_months must be > 0"):
        build_walk_forward_windows(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 3, 1),
            test_months=0,
            step_months=1,
        )

    with pytest.raises(ValueError, match="step_months must be > 0"):
        build_walk_forward_windows(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 3, 1),
            test_months=1,
            step_months=0,
        )


def test_build_walk_forward_windows_rejects_start_after_end() -> None:
    with pytest.raises(ValueError, match="start_date must be before end_date"):
        build_walk_forward_windows(
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 1),
            test_months=1,
            step_months=1,
        )


def test_build_walk_forward_windows_monthly_rolls_exact_values() -> None:
    windows = build_walk_forward_windows(
        start_date=date(2026, 1, 15),
        end_date=date(2026, 4, 10),
        test_months=1,
        step_months=1,
    )

    assert windows == [
        (date(2026, 1, 15), date(2026, 1, 31)),
        (date(2026, 2, 1), date(2026, 2, 28)),
        (date(2026, 3, 1), date(2026, 3, 31)),
        (date(2026, 4, 1), date(2026, 4, 10)),
    ]


def test_add_months_clips_end_of_month_and_rejects_negative() -> None:
    assert add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)
    assert add_months(date(2025, 1, 31), 1) == date(2025, 2, 28)

    with pytest.raises(ValueError, match="months must be >= 0"):
        add_months(date(2026, 1, 1), -1)