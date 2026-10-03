from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from backtesting.models import RunUniverse
from common.tickers import load_tickers_from_file
from trading.domain.exceptions import ValidationError
from trading.domain.strategies.contracts import StrategySpec
from trading.domain.strategies.resolution import resolve_strategy
from trading.models.market_data import BAR_CLOSE
from trading.services.market_data.protocols import MarketDataProvider, require_provider
from trading.services.strategy_catalog.resolution import UnknownCatalogStrategyError, find_catalog_strategy


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

    Derived from the bar history rather than the close-only endpoint, so a run has
    one price path and one set of gap-filling rules. Two paths would mean two cache
    entries that can disagree about which days exist.
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


def _build_monthly_universe(
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


def resolve_universe(
    *,
    tickers_file: str,
    universe_history_dir: str | None,
    start_date: date,
    end_date: date,
) -> RunUniverse:
    """The run's universe, and any warnings raised resolving it.

    Takes the two settings rather than a config object, so the backtest and
    optimizer configs can both reach it.
    """
    default_tickers = load_tickers_from_file(tickers_file)
    month_to_tickers, all_tickers, warnings = _build_monthly_universe(
        default_tickers,
        start_date,
        end_date,
        universe_history_dir,
    )

    if universe_history_dir:
        warnings.append(
            "Monthly universe reconstitution enabled from snapshot files; ticker membership can change each month."
        )

    return RunUniverse(
        default_tickers=default_tickers,
        month_to_tickers=month_to_tickers,
        all_tickers=all_tickers,
        warnings=warnings,
    )


@dataclass(frozen=True)
class RunStrategy:
    """The strategy a run simulates: the catalog key its evidence is filed under,
    the code primitive that produces its signals, and the knobs it runs with."""

    strategy_key: str
    spec: StrategySpec
    # Code defaults with the catalog row's params_json layered over them.
    params: dict[str, Any]
    # The knobs in ``params`` that differ from the primitive's code defaults.
    overrides: dict[str, Any]
    warnings: list[str] = field(default_factory=list)


def resolve_run_strategy(conn: sqlite3.Connection, label: str) -> RunStrategy:
    """Resolve a strategy label to what a backtest runs, the same way live trading does.

    A catalog key resolves through its row, so a variant runs its own
    ``params_json`` knobs. A label with no catalog row falls back to the code
    registry (aliases and keyword matching) with the primitive's defaults, and the
    run carries a warning naming what it actually ran.
    """
    try:
        resolved = find_catalog_strategy(conn, label)
    except UnknownCatalogStrategyError as error:
        raise ValidationError(str(error)) from error
    if resolved is not None:
        spec = resolve_strategy(resolved.primitive)
        params = dict(resolved.params)
        return RunStrategy(
            strategy_key=resolved.strategy_key,
            spec=spec,
            params=params,
            overrides={key: value for key, value in params.items() if spec.default_params.get(key) != value},
        )

    spec = resolve_strategy(label)
    warnings = []
    if label.strip().lower() != spec.strategy_id:
        warnings.append(
            f"Strategy '{label}' has no catalog row; ran primitive '{spec.strategy_id}' with its code defaults."
        )
    return RunStrategy(
        strategy_key=spec.strategy_id,
        spec=spec,
        params=dict(spec.default_params),
        overrides={},
        warnings=warnings,
    )
