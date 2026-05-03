from __future__ import annotations

import math

from common.coercion import coerce_float


def safe_return_pct(
    starting_equity: object,
    ending_equity: object,
) -> float | None:
    start = coerce_float(starting_equity)
    end = coerce_float(ending_equity)
    if start is None or end is None:
        return None
    if not math.isfinite(start) or not math.isfinite(end):
        return None
    if start <= 0:
        return None
    return ((end / start) - 1.0) * 100.0
