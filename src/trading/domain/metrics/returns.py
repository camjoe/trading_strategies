"""Percent return between two equity marks, in the two shapes callers need.

``total_return_pct`` is the arithmetic and insists on usable inputs;
``safe_return_pct`` is the coercing wrapper for values read out of a row, which
answers ``None`` rather than raising when the pair cannot produce a return.
Every percent return in the repo — a backtest run, a leaderboard row, an
optimizer window, an account summary, a book's day — resolves to the one below.
"""

from __future__ import annotations

import math

from common.coercion import coerce_float
from common.constants import PERCENT_SCALE


def total_return_pct(*, first_equity: float, last_equity: float) -> float:
    """Return across an interval, from its first and last equity marks (percent)."""
    if not first_equity:
        raise ValueError(f"Cannot compute return %: first_equity is 0 (last_equity={last_equity:.2f})")
    return ((last_equity / first_equity) - 1.0) * PERCENT_SCALE


def safe_return_pct(
    starting_equity: object,
    ending_equity: object,
) -> float | None:
    """``total_return_pct`` over values of unknown type, or ``None`` if they cannot serve.

    A missing mark, a non-finite one, or a non-positive start all mean the interval
    has no return to report — distinct from a return that happens to be zero.
    """
    start = coerce_float(starting_equity)
    end = coerce_float(ending_equity)
    if start is None or end is None:
        return None
    if not math.isfinite(start) or not math.isfinite(end):
        return None
    if start <= 0:
        return None
    return total_return_pct(first_equity=start, last_equity=end)
