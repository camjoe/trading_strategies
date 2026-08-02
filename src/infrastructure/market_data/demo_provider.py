"""Deterministic synthetic market data for the offline demo."""

from __future__ import annotations

import hashlib
import math
from datetime import date

import pandas as pd

from trading.models.market_data import BAR_CLOSE, BAR_COLUMNS, BAR_HIGH, BAR_LOW, BAR_OPEN, BAR_VOLUME
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

    @classmethod
    def _bar_frame(cls, ticker: str, close: pd.Series) -> pd.DataFrame:
        """Wrap a synthetic close series in bars that obey the OHLC invariants.

        High must be at least the highest of open/close and low at most the
        lowest, or indicators built on true range produce nonsense and tests
        pass against data no market could print. The spreads are deterministic
        per ticker so the demo and fixture databases stay reproducible.
        """
        seed = cls._seed(ticker)
        open_ = close.shift(1).fillna(close.iloc[0] if len(close) else 0.0)
        # Per-ticker spread between 0.4% and 1.5% of price.
        spread = 0.004 + float(seed % 11) / 1000.0
        high = pd.concat([open_, close], axis=1).max(axis=1) * (1.0 + spread)
        low = pd.concat([open_, close], axis=1).min(axis=1) * (1.0 - spread)
        volume = pd.Series(
            [float(1_000_000 + (seed + day * 79_919) % 4_000_000) for day in range(len(close))],
            index=close.index,
        )
        frame = pd.DataFrame(
            {
                BAR_OPEN: open_,
                BAR_HIGH: high,
                BAR_LOW: low,
                BAR_CLOSE: close,
                BAR_VOLUME: volume,
            }
        )
        return frame[list(BAR_COLUMNS)]

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
        normalized = [self._normalized_ticker(ticker) for ticker in tickers]
        index = pd.bdate_range(start=start_date, end=end_date)
        closes = self._close_frame(normalized, index)
        return {ticker: self._bar_frame(ticker, closes[ticker]) for ticker in normalized}

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
