from __future__ import annotations

from datetime import date
from typing import Callable

import pandas as pd


def fetch_latest_prices(
    tickers: list[str],
    *,
    fetch_close_series_fn: Callable[[str, str], pd.Series | None],
) -> dict[str, float]:
    prices: dict[str, float] = {}
    for ticker in tickers:
        close = fetch_close_series_fn(ticker, "5d")
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
    fetch_close_history_fn: Callable[[list[str], date, date], pd.DataFrame],
    today_fn: Callable[[], date],
) -> tuple[float | None, float | None]:
    ticker = benchmark_ticker.upper().strip()
    start = date.fromisoformat(created_at[:10])
    try:
        close_history = fetch_close_history_fn([ticker], start, today_fn())
        close = _extract_close_series(close_history, ticker)
    except Exception:
        return None, None

    if close is None or close.empty:
        return None, None

    start_price = float(close.iloc[0])
    end_price = float(close.iloc[-1])
    bench_equity = initial_cash * (end_price / start_price)
    bench_return_pct = ((bench_equity / initial_cash) - 1.0) * 100.0
    return bench_equity, bench_return_pct