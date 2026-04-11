from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

import pandas as pd

def build_iv_rank_proxy(
    universe: list[str],
    *,
    fetch_close_series_fn: Callable[[str, str], pd.Series | None],
) -> dict[str, float]:
    vols: dict[str, float] = {}
    for ticker in universe:
        try:
            close = fetch_close_series_fn(ticker, "1y")
            if close is None or len(close) < 30:
                continue
            daily_ret = close.pct_change().dropna()
            if daily_ret.empty:
                continue
            vol_annual = float(daily_ret.std() * (252 ** 0.5))
            vols[ticker] = vol_annual
        except Exception:
            continue

    if not vols:
        return {}

    sorted_items = sorted(vols.items(), key=lambda x: x[1])
    n = len(sorted_items)
    if n == 1:
        return {sorted_items[0][0]: 50.0}

    out: dict[str, float] = {}
    for i, (ticker, _vol) in enumerate(sorted_items):
        out[ticker] = (i / (n - 1)) * 100.0
    return out


def parse_runtime_as_of_iso(
    as_of_iso: str,
    *,
    parse_as_of_iso_fn: Callable[[str], datetime],
) -> datetime:
    return parse_as_of_iso_fn(as_of_iso)


def compute_safe_return_pct(
    starting_equity: object,
    ending_equity: object,
    *,
    safe_return_pct_fn: Callable[..., float | None],
    coerce_float_fn: Callable[[object], float | None],
) -> float | None:
    return safe_return_pct_fn(
        starting_equity,
        ending_equity,
        coerce_float_fn=coerce_float_fn,
    )


def select_account_rotation_strategy(
    conn: sqlite3.Connection,
    account: sqlite3.Row,
    as_of_iso: str,
    *,
    select_optimal_strategy_impl_fn: Callable[..., str | None],
    parse_rotation_schedule_fn: Callable[[object | None], list[str]],
    parse_as_of_iso_fn: Callable[[str], datetime],
    fetch_strategy_backtest_returns_fn: Callable[..., list[tuple[str, float]]],
    resolve_optimality_mode_fn: Callable[[sqlite3.Row], str],
    fetch_closed_rotation_episodes_fn: Callable[..., list[sqlite3.Row]] | None = None,
) -> str | None:
    return select_optimal_strategy_impl_fn(
        conn,
        account,
        as_of_iso,
        parse_rotation_schedule_fn=parse_rotation_schedule_fn,
        parse_as_of_iso_fn=parse_as_of_iso_fn,
        fetch_strategy_backtest_returns_fn=fetch_strategy_backtest_returns_fn,
        resolve_optimality_mode_fn=resolve_optimality_mode_fn,
        fetch_closed_rotation_episodes_fn=fetch_closed_rotation_episodes_fn,
    )


@dataclass
class RotationDeps:
    rotate_account_if_due_impl_fn: Callable[..., sqlite3.Row]
    is_rotation_due_fn: Callable[[sqlite3.Row], bool]
    resolve_rotation_mode_fn: Callable[[sqlite3.Row], str]
    select_optimal_strategy_fn: Callable[[sqlite3.Connection, sqlite3.Row, str], str | None]
    resolve_active_strategy_fn: Callable[[sqlite3.Row], str]
    parse_rotation_schedule_fn: Callable[[object | None], list[str]]
    next_rotation_state_fn: Callable[[sqlite3.Row, str], dict[str, object]]
    update_account_rotation_state_fn: Callable[..., None]
    get_account_fn: Callable[[sqlite3.Connection, str], sqlite3.Row]


def rotate_runtime_account_if_due(
    conn: sqlite3.Connection,
    account_name: str,
    account: sqlite3.Row,
    now_iso: str,
    deps: RotationDeps,
) -> sqlite3.Row:
    return deps.rotate_account_if_due_impl_fn(
        conn,
        account_name,
        account,
        now_iso,
        is_rotation_due_fn=deps.is_rotation_due_fn,
        resolve_rotation_mode_fn=deps.resolve_rotation_mode_fn,
        select_optimal_strategy_fn=deps.select_optimal_strategy_fn,
        resolve_active_strategy_fn=deps.resolve_active_strategy_fn,
        parse_rotation_schedule_fn=deps.parse_rotation_schedule_fn,
        next_rotation_state_fn=deps.next_rotation_state_fn,
        update_account_rotation_state_fn=deps.update_account_rotation_state_fn,
        get_account_fn=deps.get_account_fn,
    )


def validate_trade_count_range(min_trades: int, max_trades: int) -> None:
    if min_trades < 1:
        raise ValueError("--min-trades must be >= 1")
    if max_trades < min_trades:
        raise ValueError("--max-trades must be >= --min-trades")


def resolve_account_names(accounts_arg: str) -> list[str]:
    accounts = [account.strip() for account in accounts_arg.split(",") if account.strip()]
    if not accounts:
        raise ValueError("No accounts provided.")
    return accounts


def resolve_market_inputs(
    tickers_file: str,
    *,
    load_tickers_from_file_fn: Callable[[str], list[str]],
    fetch_latest_prices_fn: Callable[[list[str]], dict[str, float]],
    build_iv_rank_proxy_fn: Callable[[list[str]], dict[str, float]],
) -> tuple[list[str], dict[str, float], dict[str, float]]:
    universe = load_tickers_from_file_fn(tickers_file)
    if not universe:
        raise ValueError("Ticker universe is empty.")

    prices = fetch_latest_prices_fn(universe)
    if not prices:
        raise ValueError("Could not fetch any prices for ticker universe.")

    iv_rank_proxy = build_iv_rank_proxy_fn(universe)
    return universe, prices, iv_rank_proxy


def run_accounts(
    conn: sqlite3.Connection,
    *,
    account_names: list[str],
    universe: list[str],
    prices: dict[str, float],
    iv_rank_proxy: dict[str, float],
    min_trades: int,
    max_trades: int,
    fee: float,
    run_for_account_fn: Callable[..., int],
) -> list[tuple[str, int]]:
    results: list[tuple[str, int]] = []
    for account_name in account_names:
        executed = run_for_account_fn(
            conn=conn,
            account_name=account_name,
            universe=universe,
            prices=prices,
            iv_rank_proxy=iv_rank_proxy,
            min_trades=min_trades,
            max_trades=max_trades,
            fee=fee,
        )
        results.append((account_name, executed))
    return results
