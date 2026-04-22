"""Auto-trading market-data preparation helpers."""

from __future__ import annotations

from typing import Callable

import pandas as pd

from common.constants import ANNUALIZATION_FACTOR


def build_iv_rank_proxy(
    universe: list[str],
    *,
    fetch_close_series_fn: Callable[[str, str], pd.Series | None],
) -> dict[str, float]:
    vols: dict[str, float] = {}
    for ticker in universe:
        try:
            close = fetch_close_series_fn(ticker, "1y")
            if close is None or len(close) < 30:
                continue
            daily_ret = close.pct_change().dropna()
            if daily_ret.empty:
                continue
            vol_annual = float(daily_ret.std() * ANNUALIZATION_FACTOR)
            vols[ticker] = vol_annual
        except Exception:
            continue

    if not vols:
        return {}

    sorted_items = sorted(vols.items(), key=lambda x: x[1])
    n = len(sorted_items)
    if n == 1:
        return {sorted_items[0][0]: 50.0}

    out: dict[str, float] = {}
    for i, (ticker, _vol) in enumerate(sorted_items):
        out[ticker] = (i / (n - 1)) * 100.0
    return out
