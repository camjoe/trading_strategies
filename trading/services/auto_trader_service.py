from __future__ import annotations

import sqlite3
from typing import Callable


def build_iv_rank_proxy(
    universe: list[str],
    *,
    fetch_close_series_fn: Callable[[str, str], object],
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