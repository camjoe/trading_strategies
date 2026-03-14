from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf


def load_tickers_from_file(file_path: str) -> list[str]:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Ticker file not found: {file_path}")

    tickers: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        tokens = line.replace(",", " ").split()
        tickers.extend([t.strip().upper() for t in tokens if t.strip()])

    return list(dict.fromkeys(tickers))


def resolve_backtest_dates(
    start: str | None,
    end: str | None,
    lookback_months: int | None,
    as_of: date | None = None,
) -> tuple[date, date]:
    if start and lookback_months is not None:
        raise ValueError("Use either --start or --lookback-months, not both.")

    now = as_of or datetime.now(UTC).date()
    end_date = datetime.strptime(end, "%Y-%m-%d").date() if end else now

    if lookback_months is not None:
        if lookback_months <= 0:
            raise ValueError("lookback_months must be > 0")
        start_date = end_date - timedelta(days=int(lookback_months * 30.5))
    elif start:
        start_date = datetime.strptime(start, "%Y-%m-%d").date()
    else:
        start_date = end_date - timedelta(days=31)

    if start_date >= end_date:
        raise ValueError("start date must be before end date")

    return start_date, end_date


def _normalize_download_close(hist: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
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
    return close


def fetch_close_history(
    tickers: list[str],
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    if not tickers:
        raise ValueError("At least one ticker is required for backtesting.")

    # yfinance end date is exclusive, so advance by one day to include requested end_date.
    hist = yf.download(
        tickers=tickers,
        start=start_date.isoformat(),
        end=(end_date + timedelta(days=1)).isoformat(),
        auto_adjust=True,
        progress=False,
        group_by="column",
    )
    close = _normalize_download_close(hist, tickers)

    missing = [t for t in tickers if t not in close.columns]
    if missing:
        raise ValueError(f"Missing close history for tickers: {', '.join(missing)}")

    return close[tickers]


def fetch_benchmark_close(benchmark_ticker: str, start_date: date, end_date: date) -> pd.Series:
    close = fetch_close_history([benchmark_ticker], start_date, end_date)
    series = close[benchmark_ticker].dropna()
    if series.empty:
        raise ValueError(f"No benchmark history for {benchmark_ticker}")
    return series
