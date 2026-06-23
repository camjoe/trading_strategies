"""Auto-trading market-data preparation helpers."""

from __future__ import annotations

import logging

from common.constants import ANNUALIZATION_FACTOR
from trading.services.market_data import MarketDataProvider, get_provider

logger = logging.getLogger(__name__)


def build_iv_rank_proxy(
    universe: list[str],
    *,
    provider: MarketDataProvider | None = None,
) -> dict[str, float]:
    vols: dict[str, float] = {}
    provider = provider or get_provider()
    for ticker in universe:
        try:
            close = provider.fetch_close_series(ticker, "1y")
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
