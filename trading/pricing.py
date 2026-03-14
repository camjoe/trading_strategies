import yfinance as yf


def _fetch_close(ticker: str, **hist_kwargs: object):
    """Return the cleaned Close series from a yfinance history call, or None on failure/empty."""
    try:
        hist = yf.Ticker(ticker).history(**hist_kwargs, auto_adjust=True)
        if hist.empty:
            return None
        close = hist["Close"].dropna()
        return close if not close.empty else None
    except Exception:
        return None


def fetch_latest_prices(tickers: list[str]) -> dict[str, float]:
    prices: dict[str, float] = {}
    for ticker in tickers:
        close = _fetch_close(ticker, period="5d")
        if close is not None:
            prices[ticker] = float(close.iloc[-1])
    return prices


def benchmark_stats(benchmark_ticker: str, initial_cash: float, created_at: str) -> tuple[float | None, float | None]:
    ticker = benchmark_ticker.upper().strip()
    close = _fetch_close(ticker, start=created_at[:10], period="max")
    if close is None:
        return None, None

    start_price = float(close.iloc[0])
    end_price = float(close.iloc[-1])
    bench_equity = initial_cash * (end_price / start_price)
    bench_return_pct = ((bench_equity / initial_cash) - 1.0) * 100.0
    return bench_equity, bench_return_pct
