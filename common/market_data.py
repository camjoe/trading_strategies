from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, timedelta

import pandas as pd
import yfinance as yf


class MarketDataProvider(ABC):
    """Abstract interface for market data sources.

    Implement this class to swap out yfinance for another provider, then
    register your implementation with :func:`set_provider`.
    """

    @abstractmethod
    def fetch_ohlcv(self, ticker: str, period: str, interval: str) -> pd.DataFrame:
        """Return a normalised OHLCV DataFrame for *ticker* over *period*/*interval*.

        Raises:
            ValueError: if no data is returned for the requested ticker/period.
        """

    @abstractmethod
    def fetch_close_history(
        self,
        tickers: list[str],
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        """Return a DataFrame of daily close prices with *tickers* as columns.

        Raises:
            ValueError: if data is unavailable or tickers are missing.
        """

    @abstractmethod
    def fetch_close_series(self, ticker: str, period: str) -> pd.Series | None:
        """Return the Close series for *ticker* over *period*, or None on failure."""


class YFinanceProvider(MarketDataProvider):
    """Concrete market data provider backed by yfinance / Yahoo Finance."""

    def fetch_ohlcv(self, ticker: str, period: str, interval: str) -> pd.DataFrame:
        df = yf.download(ticker, period=period, interval=interval, auto_adjust=True, progress=False)
        if df.empty:
            raise ValueError(
                f"No data returned for ticker '{ticker}' "
                f"(period={period}, interval={interval})."
            )
        if isinstance(df.columns, pd.MultiIndex):
            if "Ticker" in df.columns.names:
                tickers_in_df = df.columns.get_level_values("Ticker")
                key = ticker if ticker in tickers_in_df else tickers_in_df[0]
                df = df.xs(key, axis=1, level="Ticker", drop_level=True)
            else:
                df.columns = df.columns.get_level_values(0)
        return df

    def fetch_close_history(
        self,
        tickers: list[str],
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        if not tickers:
            raise ValueError("At least one ticker is required.")

        # yfinance end date is exclusive — advance by one day to include end_date.
        hist = yf.download(
            tickers=tickers,
            start=start_date.isoformat(),
            end=(end_date + timedelta(days=1)).isoformat(),
            auto_adjust=True,
            progress=False,
            group_by="column",
        )

        if hist.empty:
            raise ValueError("No historical price data returned for requested tickers/date range.")

        if len(tickers) == 1:
            close = hist[["Close"]].rename(columns={"Close": tickers[0]})
        else:
            if "Close" not in hist.columns.get_level_values(0):
                raise ValueError("Downloaded price frame is missing Close column.")
            close = hist["Close"].copy()

        close = close.sort_index()
        close = close.dropna(axis=1, how="all")
        close = close.ffill().dropna(how="all")

        if close.empty:
            raise ValueError("Close price history is empty after cleaning.")

        close.index = pd.to_datetime(close.index).tz_localize(None)

        missing = [t for t in tickers if t not in close.columns]
        if missing:
            raise ValueError(f"Missing close history for tickers: {', '.join(missing)}")

        return close[tickers]

    def fetch_close_series(self, ticker: str, period: str) -> pd.Series | None:
        try:
            hist = yf.Ticker(ticker).history(period=period, auto_adjust=True)
            if hist.empty:
                return None
            close = hist["Close"].dropna()
            return close if not close.empty else None
        except Exception:
            return None


_provider: MarketDataProvider = YFinanceProvider()


def get_provider() -> MarketDataProvider:
    """Return the active market data provider."""
    return _provider


def set_provider(provider: MarketDataProvider) -> None:
    """Replace the active market data provider.

    Use this to inject a custom or stub provider (e.g. for testing):

        from common.market_data import set_provider
        set_provider(MyCustomProvider())
    """
    global _provider
    _provider = provider
