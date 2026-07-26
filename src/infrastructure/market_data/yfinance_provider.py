"""Yahoo Finance market-data adapter."""

from __future__ import annotations

import logging
import os
from datetime import date, timedelta

import pandas as pd
import yfinance as yf

from common.rate_limit import RateLimiter
from trading.services.market_data.protocols import MarketDataProvider

from .cache import _CACHE_MISS, market_data_cache_key, read_market_data_cache, write_market_data_cache

logger = logging.getLogger(__name__)

# Deterministic guard on outbound Yahoo requests (module docstring in common/rate_limit.py).
# Only actual network fetches acquire a slot — cache hits neither pace nor count. One
# limiter is built per provider instance, and the composition root builds one provider per
# run and injects it down, so all of a run's fetches share one budget.
_YF_MIN_INTERVAL_ENV = "TRADING_YF_MIN_INTERVAL_SECONDS"
_YF_MAX_CALLS_ENV = "TRADING_YF_MAX_CALLS"
# Pacing is opt-in (0 = off) so it never adds latency to normal use; set the env var to a
# small value (e.g. 0.5) to space out requests during a large cold research sweep.
_DEFAULT_YF_MIN_INTERVAL_SECONDS = 0.0
# Cumulative-call ceiling per run: far above any legitimate sweep (~tens of cold fetches),
# but a hard, zero-latency stop for an accidental unbounded loop. Env var 0 disables it.
_DEFAULT_YF_MAX_CALLS = 1000


def _env_float(name: str, default: float) -> float:
    raw = str(os.getenv(name, "")).strip()
    if not raw:
        return default
    try:
        return max(0.0, float(raw))
    except ValueError:
        logger.warning("Invalid %s=%r; using default %s", name, raw, default)
        return default


def _env_int(name: str, default: int) -> int:
    raw = str(os.getenv(name, "")).strip()
    if not raw:
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        logger.warning("Invalid %s=%r; using default %s", name, raw, default)
        return default


def build_market_data_rate_limiter() -> RateLimiter:
    """Build a yfinance call guard from env (opt-in spacing + a cumulative ceiling)."""
    max_calls = _env_int(_YF_MAX_CALLS_ENV, _DEFAULT_YF_MAX_CALLS)
    return RateLimiter(
        min_interval_seconds=_env_float(_YF_MIN_INTERVAL_ENV, _DEFAULT_YF_MIN_INTERVAL_SECONDS),
        max_total_calls=None if max_calls == 0 else max_calls,
        name="yfinance",
    )


class YFinanceProvider(MarketDataProvider):
    """Concrete market data provider backed by yfinance / Yahoo Finance."""

    def __init__(self, *, rate_limiter: RateLimiter | None = None) -> None:
        # One guard per provider (env-configured); injectable for tests.
        self._rate_limiter = rate_limiter or build_market_data_rate_limiter()

    def fetch_ohlcv(self, ticker: str, period: str, interval: str) -> pd.DataFrame:
        cache_key = market_data_cache_key("ohlcv", ticker=ticker.upper().strip(), period=period, interval=interval)
        cached = read_market_data_cache(cache_key)
        if cached is not _CACHE_MISS:
            return cached

        self._rate_limiter.acquire()
        df = yf.download(ticker, period=period, interval=interval, auto_adjust=True, progress=False)
        if df.empty:
            raise ValueError(f"No data returned for ticker '{ticker}' (period={period}, interval={interval}).")
        if isinstance(df.columns, pd.MultiIndex):
            if "Ticker" in df.columns.names:
                tickers_in_df = df.columns.get_level_values("Ticker")
                key = ticker if ticker in tickers_in_df else tickers_in_df[0]
                df = df.xs(key, axis=1, level="Ticker", drop_level=True)
            else:
                df.columns = df.columns.get_level_values(0)
        write_market_data_cache(cache_key, df)
        return df

    def fetch_close_history(self, tickers: list[str], start_date: date, end_date: date) -> pd.DataFrame:
        if not tickers:
            raise ValueError("At least one ticker is required.")

        normalized_tickers = [ticker.upper().strip() for ticker in tickers]
        cache_key = market_data_cache_key(
            "close-history",
            tickers=normalized_tickers,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
        )
        cached = read_market_data_cache(cache_key)
        if cached is not _CACHE_MISS:
            return cached

        self._rate_limiter.acquire()
        hist = yf.download(
            tickers=normalized_tickers,
            start=start_date.isoformat(),
            end=(end_date + timedelta(days=1)).isoformat(),
            auto_adjust=True,
            progress=False,
            group_by="column",
        )
        if hist.empty:
            raise ValueError("No historical price data returned for requested tickers/date range.")

        if len(normalized_tickers) == 1:
            close = hist[["Close"]].rename(columns={"Close": normalized_tickers[0]})
        else:
            if "Close" not in hist.columns.get_level_values(0):
                raise ValueError("Downloaded price frame is missing Close column.")
            close = hist["Close"].copy()

        close = close.sort_index().dropna(axis=1, how="all").ffill().dropna(how="all")
        if close.empty:
            raise ValueError("Close price history is empty after cleaning.")
        close.index = pd.to_datetime(close.index).tz_localize(None)
        missing = [ticker for ticker in normalized_tickers if ticker not in close.columns]
        if missing:
            raise ValueError(f"Missing close history for tickers: {', '.join(missing)}")
        result = close[normalized_tickers]
        write_market_data_cache(cache_key, result)
        return result

    def fetch_close_series(self, ticker: str, period: str) -> pd.Series | None:
        normalized_ticker = ticker.upper().strip()
        cache_key = market_data_cache_key("close-series", ticker=normalized_ticker, period=period)
        cached = read_market_data_cache(cache_key)
        if cached is not _CACHE_MISS:
            return cached

        # Outside the try: a RateLimitExceeded must surface, never be swallowed as a
        # fetch failure that silently returns None.
        self._rate_limiter.acquire()
        try:
            hist = yf.Ticker(normalized_ticker).history(period=period, auto_adjust=True)
            if hist.empty:
                return None
            close = hist["Close"].dropna()
            if close.empty:
                return None
            write_market_data_cache(cache_key, close)
            return close
        except Exception as exc:
            logger.warning("Failed to fetch close history for %s: %s", ticker, exc, exc_info=True)
            return None
