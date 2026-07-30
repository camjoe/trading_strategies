"""Placeholder adapter for configured market-data integrations not yet implemented."""

from __future__ import annotations

from datetime import date
from typing import NoReturn

import pandas as pd

from trading.services.market_data.protocols import MarketDataProvider


class UnavailableProvider(MarketDataProvider):
    """Placeholder provider for planned integrations not wired yet."""

    def __init__(self, provider_name: str) -> None:
        self.provider_name = provider_name

    def _raise_unavailable(self) -> NoReturn:
        raise NotImplementedError(
            f"Market data provider '{self.provider_name}' is not implemented yet. Use provider 'yfinance' for now."
        )

    def fetch_ohlcv(self, ticker: str, period: str, interval: str) -> pd.DataFrame:
        self._raise_unavailable()

    def fetch_close_history(self, tickers: list[str], start_date: date, end_date: date) -> pd.DataFrame:
        self._raise_unavailable()

    def fetch_close_series(self, ticker: str, period: str) -> pd.Series | None:
        self._raise_unavailable()

    def fetch_bar_history(
        self,
        tickers: list[str],
        start_date: date,
        end_date: date,
    ) -> dict[str, pd.DataFrame]:
        self._raise_unavailable()
