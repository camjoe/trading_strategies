from __future__ import annotations

from trading.services.sleeves.helpers import mean, resolve_window_bounds


def test_mean_returns_zero_for_empty_list() -> None:
    assert mean([]) == 0.0


def test_mean_computes_average() -> None:
    assert mean([1.0, 2.0, 3.0]) == 2.0
    assert mean([10.0]) == 10.0


def test_resolve_window_bounds_basic() -> None:
    start, end = resolve_window_bounds(as_of_iso="2026-01-10T00:00:00Z", rolling_window_days=7)
    assert end == "2026-01-10"
    assert start == "2026-01-04"  # 7 days inclusive: Jan 4–10


def test_resolve_window_bounds_clamps_to_one_day() -> None:
    start, end = resolve_window_bounds(as_of_iso="2026-03-15T00:00:00Z", rolling_window_days=0)
    assert start == end == "2026-03-15"


def test_resolve_window_bounds_one_day() -> None:
    start, end = resolve_window_bounds(as_of_iso="2026-06-01T00:00:00Z", rolling_window_days=1)
    assert start == end == "2026-06-01"
