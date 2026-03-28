from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta


def add_months(base: date, months: int) -> date:
    if months < 0:
        raise ValueError("months must be >= 0")

    month_index = (base.year * 12 + (base.month - 1)) + months
    target_year = month_index // 12
    target_month = (month_index % 12) + 1
    target_day = min(base.day, monthrange(target_year, target_month)[1])
    return date(target_year, target_month, target_day)


def build_walk_forward_windows(
    start_date: date,
    end_date: date,
    test_months: int,
    step_months: int,
) -> list[tuple[date, date]]:
    if test_months <= 0:
        raise ValueError("test_months must be > 0")
    if step_months <= 0:
        raise ValueError("step_months must be > 0")
    if start_date >= end_date:
        raise ValueError("start_date must be before end_date")

    windows: list[tuple[date, date]] = []
    cursor = date(start_date.year, start_date.month, 1)
    while cursor <= end_date:
        next_cursor = add_months(cursor, test_months)
        window_start = max(start_date, cursor)
        window_end = min(end_date, next_cursor - timedelta(days=1))
        if window_start < window_end:
            windows.append((window_start, window_end))
        cursor = add_months(cursor, step_months)

    return windows
