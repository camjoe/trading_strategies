"""Auto-trading market-data preparation helpers."""

from __future__ import annotations

import logging
from collections.abc import Mapping

import pandas as pd

from common.constants import ANNUALIZATION_FACTOR
from common.rate_limit import RateLimitExceeded
from trading.domain.bars import normalize_bar_frame
from trading.models.market_data import BAR_CLOSE
from trading.services.market_data import MarketDataProvider, require_provider

logger = logging.getLogger(__name__)

# Fixed lookback for runtime signal evaluation: covers the largest indicator window.
CLOSE_HISTORY_PERIOD = "1y"

# Runtime signals are evaluated on daily bars, matching the backtest engine.
DAILY_INTERVAL = "1d"


def fetch_bar_histories(
    universe: list[str],
    *,
    provider: MarketDataProvider | None = None,
    period: str = CLOSE_HISTORY_PERIOD,
) -> dict[str, pd.DataFrame]:
    """Fetch per-ticker daily bars once per run, shared by signal evaluation and the IV proxy.

    Bars rather than closes because strategies read indicators that can be
    sourced from any bar column — a breakout is defined on the prior window's
    true highs and lows, and a close-only history cannot express it. The backtest
    engine reads bars, so live must too or the two evaluate the same strategy
    differently.

    The provider hands back ``BAR_COLUMNS`` already; this adds only the
    gap-filling the backtest path also applies.
    """
    provider = require_provider(provider)
    histories: dict[str, pd.DataFrame] = {}
    for ticker in universe:
        # One bad ticker must never take the universe down with it.
        try:
            frame = provider.fetch_ohlcv(ticker, period, DAILY_INTERVAL)
            if frame is None or frame.empty:
                continue
            # Same gap-filling rule the backtest path applies. Without it a halted or
            # thinly-traded name reaches the signal with raw vendor gaps live and
            # forward-filled bars in a backtest, so the same rolling window can
            # produce a different value on the same date — the divergence between
            # evaluation and live trading that reading bars at all was meant to close.
            histories[ticker] = normalize_bar_frame(frame)
        except RateLimitExceeded:
            # Not a bad ticker: skipping it would truncate the universe.
            raise
        except Exception as exc:
            logger.debug("Skipping bar history for %s: %s", ticker, exc, exc_info=True)
    return histories


def build_iv_rank_proxy(
    universe: list[str],
    *,
    provider: MarketDataProvider | None = None,
    histories: Mapping[str, pd.DataFrame] | None = None,
) -> dict[str, float]:
    if histories is None:
        histories = fetch_bar_histories(universe, provider=provider)
    vols: dict[str, float] = {}
    for ticker in universe:
        try:
            bars = histories.get(ticker)
            close = None if bars is None else bars[BAR_CLOSE]
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
