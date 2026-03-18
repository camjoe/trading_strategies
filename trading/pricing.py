from datetime import date

import pandas as pd

from common.market_data import get_provider


def fetch_latest_prices(tickers: list[str]) -> dict[str, float]:
    provider = get_provider()
    prices: dict[str, float] = {}
    for ticker in tickers:
        close = provider.fetch_close_series(ticker, "5d")
        if close is not None:
            prices[ticker] = float(close.iloc[-1])
    return prices


def benchmark_stats(benchmark_ticker: str, initial_cash: float, created_at: str) -> tuple[float | None, float | None]:
    ticker = benchmark_ticker.upper().strip()
    start = date.fromisoformat(created_at[:10])
    try:
        close_df = get_provider().fetch_close_history([ticker], start, date.today())
        close_col = close_df[ticker]
        if isinstance(close_col, pd.DataFrame):
            # Some providers can return duplicate ticker columns; use the first non-empty series.
            if close_col.shape[1] == 0:
                return None, None
            close = close_col.iloc[:, 0].dropna()
        else:
            close = close_col.dropna()
    except Exception:
        return None, None
    if close.empty:
        return None, None
    start_price = float(close.iloc[0])
    end_price = float(close.iloc[-1])
    bench_equity = initial_cash * (end_price / start_price)
    bench_return_pct = ((bench_equity / initial_cash) - 1.0) * 100.0
    return bench_equity, bench_return_pct
