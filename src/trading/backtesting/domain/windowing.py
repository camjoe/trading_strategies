from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta

from trading.backtesting.optimizer_models import WalkForwardSplit
from trading.domain.exceptions import ValidationError


def shift_months(base: date, months: int) -> date:
    """Shift a date by a signed number of months, clamping the day to the target month."""
    month_index = (base.year * 12 + (base.month - 1)) + months
    target_year = month_index // 12
    target_month = (month_index % 12) + 1
    target_day = min(base.day, monthrange(target_year, target_month)[1])
    return date(target_year, target_month, target_day)


def add_months(base: date, months: int) -> date:
    if months < 0:
        raise ValidationError("months must be >= 0")
    return shift_months(base, months)


def build_walk_forward_windows(
    start_date: date,
    end_date: date,
    test_months: int,
    step_months: int,
) -> list[tuple[date, date]]:
    if test_months <= 0:
        raise ValidationError("test_months must be > 0")
    if step_months <= 0:
        raise ValidationError("step_months must be > 0")
    if start_date >= end_date:
        raise ValidationError("start_date must be before end_date")

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


def build_walk_forward_optimization_splits(
    start_date: date,
    end_date: date,
    *,
    train_months: int,
    test_months: int,
    step_months: int,
    holdout_months: int,
) -> tuple[list[WalkForwardSplit], tuple[date, date] | None]:
    """Build train/test splits for walk-forward optimization plus an untouched holdout.

    A final ``holdout_months`` interval is carved off the end and excluded from every
    training and test window. Each test window is preceded by a ``train_months`` training
    interval ending the day before the test starts. ``step_months`` must be at least
    ``test_months`` so out-of-sample windows never overlap.
    """
    if train_months <= 0:
        raise ValidationError("train_months must be > 0")
    if test_months <= 0:
        raise ValidationError("test_months must be > 0")
    if step_months <= 0:
        raise ValidationError("step_months must be > 0")
    if holdout_months < 0:
        raise ValidationError("holdout_months must be >= 0")
    if step_months < test_months:
        raise ValidationError("step_months must be >= test_months to avoid overlapping OOS windows")
    if start_date >= end_date:
        raise ValidationError("start_date must be before end_date")

    holdout: tuple[date, date] | None = None
    optimization_end = end_date
    if holdout_months > 0:
        end_month_first = date(end_date.year, end_date.month, 1)
        holdout_start = shift_months(end_month_first, 1 - holdout_months)
        if holdout_start <= start_date:
            raise ValidationError("holdout_months leaves no room for any training/test window")
        holdout = (holdout_start, end_date)
        optimization_end = holdout_start - timedelta(days=1)

    splits: list[WalkForwardSplit] = []
    opt_start = date(start_date.year, start_date.month, 1)
    test_cursor = add_months(opt_start, train_months)
    while True:
        test_end = add_months(test_cursor, test_months) - timedelta(days=1)
        if test_end > optimization_end:
            break
        train_start = max(shift_months(test_cursor, -train_months), start_date)
        train_end = test_cursor - timedelta(days=1)
        test_start = max(test_cursor, start_date)
        if train_start < train_end and test_start < test_end:
            splits.append(
                WalkForwardSplit(
                    train_start=train_start,
                    train_end=train_end,
                    test_start=test_start,
                    test_end=min(test_end, optimization_end),
                )
            )
        test_cursor = add_months(test_cursor, step_months)

    if not splits:
        raise ValidationError(
            "Date range too short for the requested train/test/holdout geometry; no windows generated."
        )

    return splits, holdout
