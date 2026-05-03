"""Auto-trading input and batch orchestration helpers."""

from __future__ import annotations

import sqlite3

from common.tickers import load_tickers_from_file
from trading.services.pricing import fetch_latest_prices
from trading.services.auto_trading.market import build_iv_rank_proxy


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


def resolve_market_inputs(tickers_file: str) -> tuple[list[str], dict[str, float], dict[str, float]]:
    universe = load_tickers_from_file(tickers_file)
    if not universe:
        raise ValueError("Ticker universe is empty.")

    prices = fetch_latest_prices(universe)
    if not prices:
        raise ValueError("Could not fetch any prices for ticker universe.")

    iv_rank_proxy = build_iv_rank_proxy(universe)
    return universe, prices, iv_rank_proxy


def _run_account_trade_loop(**kwargs) -> int:
    from trading.services.auto_trading.runtime import run_for_account

    return run_for_account(**kwargs)


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
) -> list[tuple[str, int]]:
    results: list[tuple[str, int]] = []
    for account_name in account_names:
        executed = _run_account_trade_loop(
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
