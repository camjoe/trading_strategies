import yfinance as yf


def fetch_latest_prices(tickers: list[str]) -> dict[str, float]:
    prices: dict[str, float] = {}
    for ticker in tickers:
        try:
            hist = yf.Ticker(ticker).history(period="5d", auto_adjust=True)
            if hist.empty:
                continue
            close = hist["Close"].dropna()
            if close.empty:
                continue
            prices[ticker] = float(close.iloc[-1])
        except Exception:
            # Keep report resilient if one ticker lookup fails.
            continue
    return prices


def benchmark_stats(benchmark_ticker: str, initial_cash: float, created_at: str) -> tuple[float | None, float | None]:
    ticker = benchmark_ticker.upper().strip()
    start_date = created_at[:10]
    try:
        hist = yf.Ticker(ticker).history(start=start_date, period="max", auto_adjust=True)
        if hist.empty:
            return None, None

        close = hist["Close"].dropna()
        if close.empty:
            return None, None

        start_price = float(close.iloc[0])
        end_price = float(close.iloc[-1])
        bench_equity = initial_cash * (end_price / start_price)
        bench_return_pct = ((bench_equity / initial_cash) - 1.0) * 100.0
        return bench_equity, bench_return_pct
    except Exception:
        return None, None
