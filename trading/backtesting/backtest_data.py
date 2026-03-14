from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf
from common.tickers import load_tickers_from_file as _load_tickers_from_file

DATE_FMT = "%Y-%m-%d"


def load_tickers_from_file(file_path: str) -> list[str]:
    return _load_tickers_from_file(file_path)


def _parse_date(value: str, label: str) -> date:
    try:
        return datetime.strptime(value, DATE_FMT).date()
    except ValueError as exc:
        raise ValueError(f"Invalid {label} date: {value}. Expected format is {DATE_FMT}.") from exc


def resolve_backtest_dates(
    start: str | None,
    end: str | None,
    lookback_months: int | None,
    as_of: date | None = None,
) -> tuple[date, date]:
    if start and lookback_months is not None:
        raise ValueError("Use either --start or --lookback-months, not both.")

    now = as_of or datetime.now(UTC).date()
    end_date = _parse_date(end, "end") if end else now

    if lookback_months is not None:
        if lookback_months <= 0:
            raise ValueError("lookback_months must be > 0")
        start_date = end_date - timedelta(days=int(lookback_months * 30.5))
    elif start:
        start_date = _parse_date(start, "start")
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


def _iter_month_keys(start_date: date, end_date: date) -> list[str]:
    def next_month_start(current: date) -> date:
        if current.month == 12:
            return date(current.year + 1, 1, 1)
        return date(current.year, current.month + 1, 1)

    keys: list[str] = []
    cursor = date(start_date.year, start_date.month, 1)
    while cursor <= end_date:
        keys.append(f"{cursor.year:04d}-{cursor.month:02d}")
        cursor = next_month_start(cursor)
    return keys


def build_monthly_universe(
    default_tickers: list[str],
    start_date: date,
    end_date: date,
    universe_history_dir: str | None,
) -> tuple[dict[str, list[str]], list[str], list[str]]:
    if not default_tickers:
        raise ValueError("Default ticker universe is empty.")

    month_keys = _iter_month_keys(start_date, end_date)
    month_to_tickers: dict[str, list[str]] = {}
    warnings: list[str] = []

    if not universe_history_dir:
        for month_key in month_keys:
            month_to_tickers[month_key] = list(default_tickers)
        return month_to_tickers, list(default_tickers), warnings

    history_dir = Path(universe_history_dir)
    if not history_dir.exists() or not history_dir.is_dir():
        raise ValueError(f"Universe history directory not found: {universe_history_dir}")

    all_tickers: set[str] = set(default_tickers)
    for month_key in month_keys:
        month_file = history_dir / f"{month_key}.txt"
        if not month_file.exists():
            warnings.append(
                f"Universe snapshot missing for {month_key}; falling back to default universe from {history_dir}."
            )
            month_to_tickers[month_key] = list(default_tickers)
            continue

        tickers = load_tickers_from_file(str(month_file))
        if not tickers:
            warnings.append(
                f"Universe snapshot {month_file.name} is empty; falling back to default universe."
            )
            month_to_tickers[month_key] = list(default_tickers)
            continue

        month_to_tickers[month_key] = tickers
        all_tickers.update(tickers)

    return month_to_tickers, sorted(all_tickers), warnings
