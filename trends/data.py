import pandas as pd

from common.market_data import get_provider


def fetch_data(ticker: str, period: str, interval: str, debug_columns: bool = False) -> pd.DataFrame:
    """Fetch normalised OHLCV data for *ticker* via the active MarketDataProvider.

    The *debug_columns* parameter is kept for API compatibility but has no
    effect — column normalisation is handled inside the provider.
    """
    return get_provider().fetch_ohlcv(ticker, period, interval)
