"""Auto-trading market-data preparation helpers."""

from __future__ import annotations

import logging
from collections.abc import Mapping

import pandas as pd

from common.constants import ANNUALIZATION_FACTOR
from trading.services.market_data import MarketDataProvider, require_provider

logger = logging.getLogger(__name__)

# Fixed lookback for runtime signal evaluation (D1): covers the largest indicator window.
CLOSE_HISTORY_PERIOD = "1y"


def fetch_close_histories(
    universe: list[str],
    *,
    provider: MarketDataProvider | None = None,
    period: str = CLOSE_HISTORY_PERIOD,
) -> dict[str, pd.Series]:
    """Fetch per-ticker close history once per run, shared by signal evaluation and the IV proxy."""
    provider = require_provider(provider)
    histories: dict[str, pd.Series] = {}
    for ticker in universe:
        try:
            close = provider.fetch_close_series(ticker, period)
        except Exception as exc:
            logger.debug("Skipping close history for %s: %s", ticker, exc, exc_info=True)
            continue
        if close is None or close.empty:
            continue
        histories[ticker] = close
    return histories


def build_iv_rank_proxy(
    universe: list[str],
    *,
    provider: MarketDataProvider | None = None,
    histories: Mapping[str, pd.Series] | None = None,
) -> dict[str, float]:
    if histories is None:
        histories = fetch_close_histories(universe, provider=provider)
    vols: dict[str, float] = {}
    for ticker in universe:
        try:
            close = histories.get(ticker)
            if close is None or len(close) < 30:
                continue
            daily_ret = close.pct_change().dropna()
            if daily_ret.empty:
                continue
            vol_annual = float(daily_ret.std() * ANNUALIZATION_FACTOR)
            vols[ticker] = vol_annual
        except Exception as exc:
            logger.debug("Skipping volatility for %s: %s", ticker, exc, exc_info=True)
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
