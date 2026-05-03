from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date

import pandas as pd


class MarketDataProvider(ABC):
    @abstractmethod
    def fetch_ohlcv(self, ticker: str, period: str, interval: str) -> pd.DataFrame:
        """Return a normalized OHLCV DataFrame for *ticker*."""

    @abstractmethod
    def fetch_close_history(
        self,
        tickers: list[str],
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        """Return a DataFrame of daily close prices with *tickers* as columns."""

    @abstractmethod
    def fetch_close_series(self, ticker: str, period: str) -> pd.Series | None:
        """Return the Close series for *ticker* over *period*, or None on failure."""


@dataclass(frozen=True)
class FeatureBundle:
    """Date-indexed non-price features keyed by tradable ticker."""

    ticker_features: dict[str, pd.DataFrame]
    market_features: pd.DataFrame | None = None
    warnings: tuple[str, ...] = ()

    def history_for_ticker(self, ticker: str, end_at: pd.Timestamp) -> pd.DataFrame | None:
        frame = self.ticker_features.get(ticker)
        if frame is None or frame.empty:
            return None

        cutoff = pd.Timestamp(end_at)
        if cutoff.tzinfo is not None:
            cutoff = cutoff.tz_convert(None)

        history = frame.loc[:cutoff]
        if history.empty:
            return None
        return history.copy()


class FeatureDataProvider(ABC):
    @abstractmethod
    def build_feature_bundle(
        self,
        tickers: list[str],
        start_date: date,
        end_date: date,
        close_history: pd.DataFrame,
    ) -> FeatureBundle:
        """Return aligned feature data for the requested tickers/date range."""
