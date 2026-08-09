from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd

from common.tickers import load_tickers_from_file
from trading.domain.exceptions import ValidationError
from trading.models.market_data import BAR_CLOSE
from trading.services.market_data import MarketDataProvider, require_provider

DATE_FMT = "%Y-%m-%d"


def _parse_date(value: str, label: str) -> date:
    try:
        return datetime.strptime(value, DATE_FMT).date()
    except ValueError as exc:
        raise ValidationError(f"Invalid {label} date: {value}. Expected format is {DATE_FMT}.") from exc


def resolve_backtest_dates(
    start: str | None,
    end: str | None,
    lookback_months: int | None,
    as_of: date | None = None,
) -> tuple[date, date]:
    if start and lookback_months is not None:
        raise ValidationError("Use either --start or --lookback-months, not both.")

    now = as_of or datetime.now(UTC).date()
    end_date = _parse_date(end, "end") if end else now

    if lookback_months is not None:
        if lookback_months <= 0:
            raise ValidationError("lookback_months must be > 0")
        start_date = end_date - timedelta(days=int(lookback_months * 30.5))
    elif start:
        start_date = _parse_date(start, "start")
    else:
        start_date = end_date - timedelta(days=31)

    if start_date >= end_date:
        raise ValidationError("start date must be before end date")

    return start_date, end_date


def fetch_bar_history(
    tickers: list[str],
    start_date: date,
    end_date: date,
    *,
    provider: MarketDataProvider | None = None,
) -> dict[str, pd.DataFrame]:
    """Return one daily bar frame per ticker over the requested span."""
    if not tickers:
        raise ValidationError("At least one ticker is required for backtesting.")
    provider = require_provider(provider)
    return provider.fetch_bar_history(tickers, start_date, end_date)


def fetch_benchmark_close(
    benchmark_ticker: str,
    start_date: date,
    end_date: date,
    *,
    provider: MarketDataProvider | None = None,
) -> pd.Series:
    """The benchmark's closing prices over the span.

    Reads bars rather than the close-only endpoint so a backtest has exactly one
    market-data path, with one set of gap-filling rules. Two paths over the same
    prices means two cache entries, two downloads, and two chances to disagree
    about which days exist — the hazard that ruled out keeping a close frame
    alongside a separate bar lookup in the first place.
    """
    frames = fetch_bar_history([benchmark_ticker], start_date, end_date, provider=provider)
    series = frames[benchmark_ticker][BAR_CLOSE].dropna()
    if series.empty:
        raise ValidationError(f"No benchmark history for {benchmark_ticker}")
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
        raise ValidationError("Default ticker universe is empty.")

    month_keys = _iter_month_keys(start_date, end_date)
    month_to_tickers: dict[str, list[str]] = {}
    warnings: list[str] = []

    if not universe_history_dir:
        for month_key in month_keys:
            month_to_tickers[month_key] = list(default_tickers)
        return month_to_tickers, list(default_tickers), warnings

    history_dir = Path(universe_history_dir)
    if not history_dir.exists() or not history_dir.is_dir():
        raise ValidationError(f"Universe history directory not found: {universe_history_dir}")

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
            warnings.append(f"Universe snapshot {month_file.name} is empty; falling back to default universe.")
            month_to_tickers[month_key] = list(default_tickers)
            continue

        month_to_tickers[month_key] = tickers
        all_tickers.update(tickers)

    return month_to_tickers, sorted(all_tickers), warnings
