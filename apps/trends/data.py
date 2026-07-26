from __future__ import annotations

import pandas as pd

from trading.services.market_data import MarketDataProvider


def fetch_data(
    ticker: str,
    period: str,
    interval: str,
    *,
    provider: MarketDataProvider,
) -> pd.DataFrame:
    """Fetch normalised OHLCV data for *ticker* via *provider*."""
    return provider.fetch_ohlcv(ticker, period, interval)
