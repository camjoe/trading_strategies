"""Pricing helpers for caller-facing price and benchmark lookups."""

from __future__ import annotations

import logging
from datetime import date

import pandas as pd

from trading.services.market_data import MarketDataProvider, require_provider

logger = logging.getLogger(__name__)


def fetch_latest_prices(
    tickers: list[str],
    *,
    provider: MarketDataProvider | None = None,
) -> dict[str, float]:
    provider = require_provider(provider)
    prices: dict[str, float] = {}
    for ticker in tickers:
        close = provider.fetch_close_series(ticker, "5d")
        if close is not None:
            prices[ticker] = float(close.iloc[-1])
    return prices


def _extract_close_series(close_history: pd.DataFrame | None, ticker: str) -> pd.Series | None:
    if close_history is None:
        return None
    close_col = close_history[ticker]
    if isinstance(close_col, pd.DataFrame):
        if close_col.shape[1] == 0:
            return None
        return close_col.iloc[:, 0].dropna()
    return close_col.dropna()


def benchmark_stats(
    benchmark_ticker: str,
    initial_cash: float,
    created_at: str,
    *,
    provider: MarketDataProvider | None = None,
) -> tuple[float | None, float | None]:
    ticker = benchmark_ticker.upper().strip()
    start = date.fromisoformat(created_at[:10])
    try:
        active_provider = require_provider(provider)
        close_history = active_provider.fetch_close_history([ticker], start, date.today())
        close = _extract_close_series(close_history, ticker)
    except Exception as exc:
        logger.warning("Failed to fetch benchmark data for %s: %s", benchmark_ticker, exc, exc_info=True)
        return None, None

    if close is None or close.empty:
        return None, None

    if not initial_cash:
        return None, None

    start_price = float(close.iloc[0])
    end_price = float(close.iloc[-1])
    bench_equity = initial_cash * (end_price / start_price)
    bench_return_pct = ((bench_equity / initial_cash) - 1.0) * 100.0
    return bench_equity, bench_return_pct
