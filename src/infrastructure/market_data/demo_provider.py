"""Deterministic synthetic market data for the offline demo."""

from __future__ import annotations

import hashlib
import math
from datetime import date

import pandas as pd

from trading.services.market_data.protocols import MarketDataProvider


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
