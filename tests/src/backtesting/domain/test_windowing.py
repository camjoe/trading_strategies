from __future__ import annotations

from datetime import date

import pytest
from hypothesis import given, settings, strategies as st

from backtesting.domain.windowing import add_months, resolve_run_window


def test_add_months_clips_end_of_month_and_rejects_negative() -> None:
    assert add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)
    assert add_months(date(2025, 1, 31), 1) == date(2025, 2, 28)

    with pytest.raises(ValueError, match="months must be >= 0"):
        add_months(date(2026, 1, 1), -1)


def test_resolve_run_window_conflict_raises() -> None:
    with pytest.raises(ValueError, match="Use either --start or --lookback-months"):
        resolve_run_window("2026-01-01", None, 1)


def test_resolve_run_window_default_window() -> None:
    start, end = resolve_run_window(None, "2026-03-14", None)
    assert start == date(2026, 2, 11)
    assert end == date(2026, 3, 14)


def test_resolve_run_window_invalid_range_raises() -> None:
    with pytest.raises(ValueError, match="start date must be before end date"):
        resolve_run_window("2026-03-14", "2026-03-14", None)


def test_resolve_run_window_rejects_invalid_start_format() -> None:
    with pytest.raises(ValueError, match="Invalid start date"):
        resolve_run_window("2026/03/14", None, None)


def test_resolve_run_window_rejects_non_positive_lookback() -> None:
    with pytest.raises(ValueError, match="lookback_months must be > 0"):
        resolve_run_window(None, "2026-03-14", 0)


def test_resolve_run_window_uses_as_of_when_end_missing() -> None:
    start, end = resolve_run_window(None, None, None, as_of=date(2026, 3, 20))

    assert start == date(2026, 2, 17)
    assert end == date(2026, 3, 20)


@settings(max_examples=30, deadline=None)
@given(
    as_of=st.dates(min_value=date(2000, 1, 1), max_value=date(2100, 12, 31)),
    lookback_months=st.integers(min_value=1, max_value=24),
)
def test_resolve_run_window_lookback_property(as_of: date, lookback_months: int) -> None:
    start, end = resolve_run_window(
        start=None,
        end=None,
        lookback_months=lookback_months,
        as_of=as_of,
    )

    assert end == as_of
    assert start < end
    assert (end - start).days == int(lookback_months * 30.5)
