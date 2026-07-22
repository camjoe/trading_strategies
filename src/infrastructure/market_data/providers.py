from __future__ import annotations

import logging
import hashlib
import math
from datetime import date, timedelta
from typing import NoReturn

import pandas as pd
import yfinance as yf

from trading.services.market_data.protocols import MarketDataProvider

from .cache import _CACHE_MISS
from .cache import market_data_cache_key
from .cache import read_market_data_cache
from .cache import write_market_data_cache

logger = logging.getLogger(__name__)


class DemoMarketDataProvider(MarketDataProvider):
    """Deterministic synthetic daily market data for offline demonstrations."""

    @staticmethod
    def _normalized_ticker(ticker: str) -> str:
        normalized = ticker.upper().strip()
        if not normalized:
            raise ValueError("Ticker cannot be empty.")
        return normalized

    @staticmethod
    def _seed(ticker: str) -> int:
        digest = hashlib.sha256(ticker.encode("utf-8")).digest()
        return int.from_bytes(digest[:8], "big")

    @classmethod
    def _close_frame(cls, tickers: list[str], index: pd.DatetimeIndex) -> pd.DataFrame:
        values: dict[str, list[float]] = {}
        for ticker in tickers:
            seed = cls._seed(ticker)
            base = 40.0 + float(seed % 16_000) / 100.0
            drift = 0.00025 + float((seed >> 8) % 35) / 100_000.0
            phase = float((seed >> 16) % 628) / 100.0
            values[ticker] = [
                round(base * (1.0 + drift * day + 0.018 * math.sin(day / 4.7 + phase)), 4) for day in range(len(index))
            ]
        return pd.DataFrame(values, index=index)

    def fetch_close_history(self, tickers: list[str], start_date: date, end_date: date) -> pd.DataFrame:
        if not tickers:
            raise ValueError("At least one ticker is required.")
        if end_date < start_date:
            raise ValueError("end_date must be on or after start_date.")
        normalized = [self._normalized_ticker(ticker) for ticker in tickers]
        index = pd.bdate_range(start=start_date, end=end_date)
        return self._close_frame(normalized, index)

    def fetch_close_series(self, ticker: str, period: str) -> pd.Series | None:
        days = {"5d": 5, "1mo": 22, "3mo": 66, "6mo": 132, "1y": 252, "2y": 504}.get(period, 252)
        end = date.today()
        index = pd.bdate_range(end=end, periods=days)
        normalized = self._normalized_ticker(ticker)
        return self._close_frame([normalized], index)[normalized]

    def fetch_ohlcv(self, ticker: str, period: str, interval: str) -> pd.DataFrame:
        if interval not in {"1d", "1wk", "1mo"}:
            raise ValueError("Demo market data supports daily, weekly, and monthly intervals.")
        close = self.fetch_close_series(ticker, period)
        assert close is not None
        frame = pd.DataFrame(index=close.index)
        frame["Open"] = close * 0.997
        frame["High"] = close * 1.008
        frame["Low"] = close * 0.992
        frame["Close"] = close
        seed = self._seed(self._normalized_ticker(ticker))
        frame["Volume"] = [1_000_000 + (seed + day * 79_919) % 4_000_000 for day in range(len(frame))]
        if interval == "1wk":
            frame = (
                frame.resample("W-FRI")
                .agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"})
                .dropna()
            )
        elif interval == "1mo":
            frame = (
                frame.resample("ME")
                .agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"})
                .dropna()
            )
        return frame


class YFinanceProvider(MarketDataProvider):
    """Concrete market data provider backed by yfinance / Yahoo Finance."""

    def fetch_ohlcv(self, ticker: str, period: str, interval: str) -> pd.DataFrame:
        cache_key = market_data_cache_key(
            "ohlcv",
            ticker=ticker.upper().strip(),
            period=period,
            interval=interval,
        )
        cached = read_market_data_cache(cache_key)
        if cached is not _CACHE_MISS:
            return cached

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

    def fetch_close_history(
        self,
        tickers: list[str],
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
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

        close = close.sort_index()
        close = close.dropna(axis=1, how="all")
        close = close.ffill().dropna(how="all")

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
        cache_key = market_data_cache_key(
            "close-series",
            ticker=normalized_ticker,
            period=period,
        )
        cached = read_market_data_cache(cache_key)
        if cached is not _CACHE_MISS:
            return cached

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

    def fetch_close_history(
        self,
        tickers: list[str],
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        self._raise_unavailable()

    def fetch_close_series(self, ticker: str, period: str) -> pd.Series | None:
        self._raise_unavailable()
