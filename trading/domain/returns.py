from __future__ import annotations

from typing import Callable


def safe_return_pct(
    starting_equity: object,
    ending_equity: object,
    *,
    coerce_float_fn: Callable[[object], float | None],
) -> float | None:
    start = coerce_float_fn(starting_equity)
    end = coerce_float_fn(ending_equity)
    if start is None or end is None:
        return None
    if start <= 0:
        return None
    return ((end / start) - 1.0) * 100.0
