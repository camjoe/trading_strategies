from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
import json
import os
from typing import Callable, Mapping

import pandas as pd
import yfinance as yf

from trends.tickers import load_ticker_categories


_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_PROVIDER_NAME = "yfinance"
_DEFAULT_MARKET_DATA_CONFIG_PATH = _REPO_ROOT / "local" / "market_data_config.json"


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


class UnavailableProvider(MarketDataProvider):
    """Placeholder provider for planned integrations not wired yet."""

    def __init__(self, provider_name: str) -> None:
        self.provider_name = provider_name

    def _raise_unavailable(self) -> None:
        raise NotImplementedError(
            f"Market data provider '{self.provider_name}' is not implemented yet. "
            "Use provider 'yfinance' for now."
        )

    def fetch_ohlcv(self, ticker: str, period: str, interval: str) -> pd.DataFrame:
        self._raise_unavailable()

    def fetch_close_history(
        self,
        tickers: list[str],
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        self._raise_unavailable()

    def fetch_close_series(self, ticker: str, period: str) -> pd.Series | None:
        self._raise_unavailable()


_PROVIDER_FACTORIES: dict[str, Callable[[], MarketDataProvider]] = {
    "yfinance": YFinanceProvider,
    # Planned providers: configurable names now, implementation to follow.
    "yahooquery": lambda: UnavailableProvider("yahooquery"), # wrapper around yahoo api (unoffical), whereas yfinance is a scraper
    "pandas-datareader": lambda: UnavailableProvider("pandas-datareader"), # can pull data from places like alpha and tiingo or iex into pandas dataframes
    "alpha_vantage": lambda: UnavailableProvider("alpha_vantage"), # good lightweight, has bulit-in MACD, RSI
    "tiingo": lambda: UnavailableProvider("tiingo"), # yfinance alternative - US stocks and crypto (good for backtesting large datasets - so is FMP)
    "stooq": lambda: UnavailableProvider("stooq"), # Historical Data  - Good for EOD data (Marketstack is alternative), global assets
    "polygon-api-client": lambda: UnavailableProvider("polygon-api-client"), # Serious real-time data, real-time websocket feeds, documentation
    "ccxt": lambda: UnavailableProvider("ccxt"),
    # Alpaca - Good for real-time data, serious about trading
    # Good for screener or valuation mode - FMP
    # Finnhub, versaile, new, quotes, technicals
}

_provider: MarketDataProvider = YFinanceProvider()
_provider_name = _DEFAULT_PROVIDER_NAME
_provider_source = "default"
_provider_config_mtime: float | None = None
_feature_provider: FeatureDataProvider = ProxyFeatureDataProvider()


def _config_path() -> Path:
    raw = str(os.getenv("TRADING_MARKET_DATA_CONFIG", "")).strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return _DEFAULT_MARKET_DATA_CONFIG_PATH


def _provider_name_from_file(config_path: Path) -> str | None:
    if not config_path.exists():
        return None
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    value = str(payload.get("provider", "")).strip().lower()
    return value or None


def _resolve_provider_name() -> str:
    env_name = str(os.getenv("TRADING_MARKET_DATA_PROVIDER", "")).strip().lower()
    if env_name:
        return env_name

    file_name = _provider_name_from_file(_config_path())
    if file_name:
        return file_name

    return _DEFAULT_PROVIDER_NAME


def _sync_provider_from_config() -> None:
    global _provider, _provider_name, _provider_source, _provider_config_mtime

    target_name = _resolve_provider_name()
    factory = _PROVIDER_FACTORIES.get(target_name)
    if factory is None:
        supported = ", ".join(sorted(_PROVIDER_FACTORIES))
        raise ValueError(f"Unsupported market data provider '{target_name}'. Supported values: {supported}")

    _provider = factory()
    _provider_name = target_name
    _provider_source = "config"

    config_path = _config_path()
    if config_path.exists():
        _provider_config_mtime = config_path.stat().st_mtime
    else:
        _provider_config_mtime = None


def _maybe_reload_provider_from_config() -> None:
    if _provider_source != "config":
        return

    config_path = _config_path()
    if not config_path.exists():
        if _provider_config_mtime is not None:
            _sync_provider_from_config()
        return

    current_mtime = config_path.stat().st_mtime
    if _provider_config_mtime is None or current_mtime != _provider_config_mtime:
        _sync_provider_from_config()


def get_provider() -> MarketDataProvider:
    """Return the active market data provider."""
    _maybe_reload_provider_from_config()
    return _provider


def set_provider(provider: MarketDataProvider) -> None:
    """Replace the active market data provider.

    Use this to inject a custom or stub provider (e.g. for testing):

        from common.market_data import set_provider
        set_provider(MyCustomProvider())
    """
    global _provider, _provider_name, _provider_source
    _provider = provider
    _provider_name = provider.__class__.__name__
    _provider_source = "manual"


def set_provider_by_name(name: str) -> None:
    """Set provider by configured registry name (e.g. yfinance)."""
    global _provider, _provider_name, _provider_source
    key = name.strip().lower()
    factory = _PROVIDER_FACTORIES.get(key)
    if factory is None:
        supported = ", ".join(sorted(_PROVIDER_FACTORIES))
        raise ValueError(f"Unsupported market data provider '{name}'. Supported values: {supported}")
    _provider = factory()
    _provider_name = key
    _provider_source = "manual"


def reload_provider_from_config() -> str:
    """Force reload provider using env/config precedence and return provider name."""
    _sync_provider_from_config()
    return _provider_name


def get_provider_name() -> str:
    """Return the active provider identifier."""
    _maybe_reload_provider_from_config()
    return _provider_name


def supported_provider_names() -> tuple[str, ...]:
    """Return supported provider identifiers, including planned placeholders."""
    return tuple(sorted(_PROVIDER_FACTORIES))


def get_feature_provider() -> FeatureDataProvider:
    """Return the active non-price feature provider."""
    return _feature_provider


def set_feature_provider(provider: FeatureDataProvider) -> None:
    """Replace the active non-price feature provider."""
    global _feature_provider
    _feature_provider = provider


_sync_provider_from_config()
