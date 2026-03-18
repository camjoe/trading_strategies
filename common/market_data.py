from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Mapping

import pandas as pd
import yfinance as yf

from trends.tickers import load_ticker_categories


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
    """Abstract interface for date-indexed non-price feature sources."""

    @abstractmethod
    def build_feature_bundle(
        self,
        tickers: list[str],
        start_date: date,
        end_date: date,
        close_history: pd.DataFrame,
    ) -> FeatureBundle:
        """Return aligned feature data for the requested tickers/date range."""


class ProxyFeatureDataProvider(FeatureDataProvider):
    """Free-first proxy feature provider using sector ETFs and market-risk series."""

    def __init__(
        self,
        *,
        category_file: str = "trends/assets/ticker_categories.txt",
        category_proxy_map: Mapping[str, str] | None = None,
        topic_lookback: int = 20,
        macro_lookback: int = 20,
    ) -> None:
        self.category_file = category_file
        self.category_proxy_map = {
            "tech": "XLK",
            "technology": "XLK",
            "energy": "XLE",
            "banks": "XLF",
            "financials": "XLF",
            "etf": "SPY",
            **{(key.strip().lower()): value.strip().upper() for key, value in (category_proxy_map or {}).items()},
        }
        self.topic_lookback = topic_lookback
        self.macro_lookback = macro_lookback

    def _load_proxy_map(self, tickers: list[str]) -> tuple[dict[str, str], list[str]]:
        warnings: list[str] = []
        ticker_to_proxy: dict[str, str] = {}
        category_path = Path(self.category_file)
        if category_path.exists():
            categories = load_ticker_categories(str(category_path))
            for category, category_tickers in categories.items():
                proxy = self.category_proxy_map.get(category)
                if proxy is None:
                    continue
                for ticker in category_tickers:
                    ticker_to_proxy.setdefault(ticker.upper(), proxy)
        else:
            warnings.append(
                f"Category file '{self.category_file}' not found; topic proxy mappings will only be available for proxy ETFs in the universe."
            )

        known_proxies = set(self.category_proxy_map.values()) | {"SPY", "QQQ", "IWM", "TLT"}
        for ticker in tickers:
            upper = ticker.upper()
            if upper in known_proxies:
                ticker_to_proxy.setdefault(upper, upper)

        return ticker_to_proxy, warnings

    def build_feature_bundle(
        self,
        tickers: list[str],
        start_date: date,
        end_date: date,
        close_history: pd.DataFrame,
    ) -> FeatureBundle:
        if close_history.empty:
            return FeatureBundle(ticker_features={})

        ticker_to_proxy, warnings = self._load_proxy_map(tickers)
        proxy_tickers = sorted(set(ticker_to_proxy.values()) | {"SPY", "TLT", "^VIX"})
        padded_start = start_date - timedelta(days=max(self.topic_lookback, self.macro_lookback) * 4)

        try:
            proxy_close = get_provider().fetch_close_history(proxy_tickers, padded_start, end_date)
        except Exception as exc:
            return FeatureBundle(
                ticker_features={},
                warnings=tuple(warnings + [f"Proxy feature data unavailable: {exc}"]),
            )

        target_index = pd.to_datetime(close_history.index)
        if getattr(target_index, "tz", None) is not None:
            target_index = target_index.tz_convert(None)
        proxy_close = proxy_close.reindex(target_index).ffill()

        topic_returns = proxy_close.pct_change(self.topic_lookback)
        topic_trend_gap = (proxy_close / proxy_close.rolling(self.topic_lookback).mean()) - 1.0

        equity_bond_spread = proxy_close["SPY"].pct_change(self.macro_lookback) - proxy_close["TLT"].pct_change(self.macro_lookback)
        vix_pressure = (proxy_close["^VIX"] / proxy_close["^VIX"].rolling(self.macro_lookback).mean()) - 1.0
        macro_risk_on_score = equity_bond_spread - vix_pressure.fillna(0.0)

        market_features = pd.DataFrame(
            {
                "macro_equity_bond_spread": equity_bond_spread,
                "macro_vix_pressure": vix_pressure,
                "macro_risk_on_score": macro_risk_on_score,
            },
            index=target_index,
        )

        unmapped: list[str] = []
        ticker_features: dict[str, pd.DataFrame] = {}
        for ticker in tickers:
            frame = market_features.copy()
            proxy_ticker = ticker_to_proxy.get(ticker.upper())
            if proxy_ticker and proxy_ticker in proxy_close.columns:
                frame["topic_proxy_rel_strength"] = topic_returns[proxy_ticker] - topic_returns["SPY"]
                frame["topic_proxy_trend_gap"] = topic_trend_gap[proxy_ticker]
                frame["topic_proxy_available"] = 1.0
            else:
                unmapped.append(ticker)
                frame["topic_proxy_rel_strength"] = float("nan")
                frame["topic_proxy_trend_gap"] = float("nan")
                frame["topic_proxy_available"] = 0.0
            ticker_features[ticker] = frame

        if unmapped:
            warnings.append(
                "Topic proxy mappings were unavailable for: " + ", ".join(sorted(unmapped))
            )

        warnings.append(
            "Proxy features use sector/theme ETFs plus SPY, TLT, and ^VIX as free-first substitutes for topic and macro sentiment."
        )

        return FeatureBundle(
            ticker_features=ticker_features,
            market_features=market_features,
            warnings=tuple(warnings),
        )


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
_feature_provider: FeatureDataProvider = ProxyFeatureDataProvider()


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


def get_feature_provider() -> FeatureDataProvider:
    """Return the active non-price feature provider."""
    return _feature_provider


def set_feature_provider(provider: FeatureDataProvider) -> None:
    """Replace the active non-price feature provider."""
    global _feature_provider
    _feature_provider = provider
