from __future__ import annotations

import pandas as pd

from trading.models.market_data import BAR_CLOSE, BAR_HIGH, BAR_LOW, BAR_OPEN, BAR_VOLUME
from trading.services.market_data import MarketDataProvider

_DISPLAY_COLUMNS = {
    BAR_OPEN: "Open",
    BAR_HIGH: "High",
    BAR_LOW: "Low",
    BAR_CLOSE: "Close",
    BAR_VOLUME: "Volume",
}


def fetch_data(
    ticker: str,
    period: str,
    interval: str,
    *,
    provider: MarketDataProvider,
) -> pd.DataFrame:
    """Fetch normalised OHLCV data for *ticker* via *provider*."""
    return provider.fetch_ohlcv(ticker, period, interval).rename(columns=_DISPLAY_COLUMNS)
