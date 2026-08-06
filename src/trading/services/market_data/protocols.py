from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date

import pandas as pd


class MarketDataProvider(ABC):
    @abstractmethod
    def fetch_ohlcv(self, ticker: str, period: str, interval: str) -> pd.DataFrame:
        """Return a bar frame for one *ticker* over a relative *period* and *interval*.

        Carries exactly ``BAR_COLUMNS``, in that order, or raises — the same
        vocabulary ``fetch_bar_history`` returns. The vendor's own spelling never
        leaves the adapter.

        Distinct from ``fetch_bar_history`` in shape, not vocabulary: one ticker
        over a relative period at any supported interval, rather than many
        tickers over a date range at daily resolution.
        """

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

    @abstractmethod
    def fetch_bar_history(
        self,
        tickers: list[str],
        start_date: date,
        end_date: date,
    ) -> dict[str, pd.DataFrame]:
        """Return one daily bar frame per ticker, keyed by ticker.

        Each frame is indexed by date and carries exactly ``BAR_COLUMNS``
        (see ``trading.models.market_data.constants``) — lower-case, in that
        order, whatever the vendor calls them. Every requested ticker gets an
        entry or the call raises; a partially-populated result would let a
        caller silently backtest a smaller universe than it asked for.

        The bulk, date-bounded, already-normalized read the simulation engine
        runs on.
        """


def require_provider(provider: MarketDataProvider | None) -> MarketDataProvider:
    """Return *provider*, or raise if it was not injected.

    The market-data provider must flow from a composition root (built via
    ``build_provider()``); there is no global locator to fall back on.
    """
    if provider is None:
        raise ValueError(
            "A MarketDataProvider must be injected; build one via build_provider() at a composition root."
        )
    return provider


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


def require_feature_provider(provider: FeatureDataProvider | None) -> FeatureDataProvider:
    """Return *provider*, or raise if it was not injected.

    The feature provider must flow from a composition root (built via
    ``build_feature_provider()``); there is no global locator to fall back on.
    """
    if provider is None:
        raise ValueError(
            "A FeatureDataProvider must be injected; build one via build_feature_provider() at a composition root."
        )
    return provider
