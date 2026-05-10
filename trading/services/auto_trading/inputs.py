"""Auto-trading input and batch orchestration helpers."""

from __future__ import annotations

import sqlite3

from common.tickers import load_tickers_from_file
from trading.services.pricing import fetch_latest_prices
from trading.services.auto_trading.market import build_iv_rank_proxy

# Default execution mode keeps existing account-scoped behavior.
EXECUTION_MODE_ACCOUNT = "account"
# New sleeve mode enables sleeve intent generation.
EXECUTION_MODE_SLEEVE = "sleeve"
SUPPORTED_EXECUTION_MODES = {
    EXECUTION_MODE_ACCOUNT,
    EXECUTION_MODE_SLEEVE,
}


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


def validate_execution_mode(execution_mode: str) -> str:
    normalized_mode = execution_mode.strip().lower()
    if normalized_mode not in SUPPORTED_EXECUTION_MODES:
        options = ", ".join(sorted(SUPPORTED_EXECUTION_MODES))
        raise ValueError(f"execution_mode must be one of: {options}")
    return normalized_mode


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
    execution_mode: str = EXECUTION_MODE_ACCOUNT,
) -> list[tuple[str, int]]:
    resolved_execution_mode = validate_execution_mode(execution_mode)
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
            execution_mode=resolved_execution_mode,
        )
        results.append((account_name, executed))
    return results
