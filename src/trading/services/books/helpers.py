"""Shared utilities for the books service package."""

from __future__ import annotations

from datetime import timedelta

from common.time import parse_utc_iso


def resolve_window_bounds(
    *,
    as_of_iso: str,
    rolling_window_days: int,
) -> tuple[str, str]:
    """Return an inclusive (start_date, end_date) ISO pair for a rolling window.

    The window is ``rolling_window_days`` calendar days ending on ``as_of_iso``
    (inclusive on both ends).
    """
    window_days = max(1, int(rolling_window_days))
    as_of_date = parse_utc_iso(as_of_iso).date()
    start_date = as_of_date - timedelta(days=window_days - 1)
    return start_date.isoformat(), as_of_date.isoformat()
