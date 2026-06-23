import pandas as pd

from trading.services.market_data import MarketDataProvider


def fetch_data(
    ticker: str,
    period: str,
    interval: str,
    *,
    provider: MarketDataProvider,
    debug_columns: bool = False,
) -> pd.DataFrame:
    """Fetch normalised OHLCV data for *ticker* via *provider*.

    The *debug_columns* parameter is kept for API compatibility but has no
    effect — column normalisation is handled inside the provider.
    """
    return provider.fetch_ohlcv(ticker, period, interval)
