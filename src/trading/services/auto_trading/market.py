"""Auto-trading market-data preparation helpers."""

from __future__ import annotations

import logging
from collections.abc import Mapping

import pandas as pd

from common.constants import ANNUALIZATION_FACTOR
from trading.domain.bars import normalize_bar_frame
from trading.models.market_data.constants import BAR_CLOSE, BAR_COLUMNS
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

    Column names are normalized to the repo's own bar vocabulary, so nothing
    above this layer has to know the vendor's spelling.
    """
    provider = require_provider(provider)
    histories: dict[str, pd.DataFrame] = {}
    for ticker in universe:
        try:
            frame = provider.fetch_ohlcv(ticker, period, DAILY_INTERVAL)
        except Exception as exc:
            logger.debug("Skipping bar history for %s: %s", ticker, exc, exc_info=True)
            continue
        if frame is None or frame.empty:
            continue
        renamed = _rename_bar_columns(frame)
        if renamed is None:
            logger.debug("Skipping bar history for %s: missing bar columns %s", ticker, list(frame.columns))
            continue
        # Same gap-filling rule the backtest path applies. Without it a halted or
        # thinly-traded name reaches the signal with raw vendor gaps live and
        # forward-filled bars in a backtest, so the same rolling window can
        # produce a different value on the same date — the divergence between
        # evaluation and live trading that reading bars at all was meant to close.
        histories[ticker] = normalize_bar_frame(renamed)
    return histories


def _rename_bar_columns(frame: pd.DataFrame) -> pd.DataFrame | None:
    """Rename a vendor OHLCV frame to the repo's bar columns, or None if incomplete."""
    lowered = {str(column).lower(): column for column in frame.columns}
    if any(name not in lowered for name in BAR_COLUMNS):
        return None
    return frame[[lowered[name] for name in BAR_COLUMNS]].set_axis(list(BAR_COLUMNS), axis=1)


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
