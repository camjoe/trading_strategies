"""An in-memory market-data provider that serves one scenario path's bars.

The scenario bench generates a bar-set per Monte Carlo path (backtesting domain),
then wraps it in this provider so the simulation engine reads it through the same
``MarketDataProvider`` port as any real adapter. It holds fully materialized
frames and only slices them; it generates nothing itself.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date

import pandas as pd

from trading.models.market_data import BAR_CLOSE
from trading.services.market_data.protocols import MarketDataProvider


class ScenarioMarketDataProvider(MarketDataProvider):
    def __init__(self, frames: Mapping[str, pd.DataFrame]) -> None:
        self._frames = dict(frames)

    def fetch_bar_history(
        self,
        tickers: list[str],
        start_date: date,
        end_date: date,
    ) -> dict[str, pd.DataFrame]:
        if not tickers:
            raise ValueError("At least one ticker is required.")
        if end_date < start_date:
            raise ValueError("end_date must be on or after start_date.")

        start = pd.Timestamp(start_date)
        end = pd.Timestamp(end_date)
        result: dict[str, pd.DataFrame] = {}
        for ticker in tickers:
            frame = self._frames.get(ticker)
            if frame is None:
                raise ValueError(f"Scenario has no generated bars for '{ticker}'.")
            result[ticker] = frame.loc[start:end]
        return result

    def fetch_close_history(
        self,
        tickers: list[str],
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        frames = self.fetch_bar_history(tickers, start_date, end_date)
        return pd.DataFrame({ticker: frame[BAR_CLOSE] for ticker, frame in frames.items()})

    def fetch_close_series(self, ticker: str, period: str) -> pd.Series | None:
        raise NotImplementedError("ScenarioMarketDataProvider serves only date-bounded history.")

    def fetch_ohlcv(self, ticker: str, period: str, interval: str) -> pd.DataFrame:
        raise NotImplementedError("ScenarioMarketDataProvider serves only date-bounded history.")
