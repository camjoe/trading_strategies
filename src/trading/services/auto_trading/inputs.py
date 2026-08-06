"""Auto-trading input and batch orchestration helpers."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Mapping

import pandas as pd

from trading.domain.broker_connection import BrokerConnection
from trading.domain.feature_provider import FeatureFetcherSet
from trading.models import AccountRecord
from trading.models.books import BookRecord
from trading.models.execution import AccountRunResult
from trading.services.accounts import get_account
from trading.services.auto_trading.market import build_iv_rank_proxy, fetch_bar_histories
from trading.services.books.book_assignments import enumerate_trading_books
from trading.services.market_data import MarketDataProvider
from trading.services.market_data.lookups import fetch_latest_prices


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


def resolve_run_universe(conn: sqlite3.Connection, account_names: list[str]) -> list[str]:
    """Union the trade symbols of every book the run will trade.

    Selection is book-scoped (``book_intents``), but the fetch is one pass for
    the whole run, so anything a book may select has to be in it. Deriving the
    fetch set from the same column selection reads keeps the two from drifting:
    a symbol a book can pick is a symbol this run priced.

    Raises:
        ValueError: If no book across *account_names* carries a symbol.
    """
    seen: dict[str, None] = {}
    for account_name in account_names:
        account = get_account(conn, account_name)
        for trading_book in enumerate_trading_books(conn, account_id=account.id):
            for symbol in _book_symbols(trading_book.book):
                seen[symbol] = None
    if not seen:
        raise ValueError(f"No trading book across {', '.join(account_names)} carries any symbol.")
    return list(seen)


def _book_symbols(book: BookRecord) -> list[str]:
    symbols = json.loads(book.trade_symbols) if book.trade_symbols else []
    if not isinstance(symbols, list):
        return []
    return [str(symbol) for symbol in symbols]


def resolve_market_inputs(
    universe: list[str],
    *,
    provider: MarketDataProvider | None = None,
) -> tuple[list[str], dict[str, float], dict[str, float], dict[str, pd.DataFrame]]:
    if not universe:
        raise ValueError("Ticker universe is empty.")

    prices = fetch_latest_prices(universe, provider=provider)
    if not prices:
        raise ValueError("Could not fetch any prices for ticker universe.")

    # One fetch pass feeds both signal evaluation and the IV-rank proxy (cached per run).
    histories = fetch_bar_histories(universe, provider=provider)
    iv_rank_proxy = build_iv_rank_proxy(universe, histories=histories)
    return universe, prices, iv_rank_proxy, histories


def _run_account_trade_loop(
    *,
    broker_factory: Callable[[AccountRecord], BrokerConnection],
    feature_fetchers: FeatureFetcherSet,
    provider: MarketDataProvider | None = None,
    **kwargs,
) -> AccountRunResult:
    from trading.services.auto_trading.runtime import run_for_account

    return run_for_account(
        **kwargs,
        broker_factory=broker_factory,
        feature_fetchers=feature_fetchers,
        provider=provider,
    )


def run_accounts(
    conn: sqlite3.Connection,
    *,
    account_names: list[str],
    universe: list[str],
    prices: dict[str, float],
    iv_rank_proxy: dict[str, float],
    max_trades: int,
    fee: float,
    histories: Mapping[str, pd.DataFrame] | None = None,
    broker_factory: Callable[[AccountRecord], BrokerConnection],
    feature_fetchers: FeatureFetcherSet,
    provider: MarketDataProvider | None = None,
) -> list[AccountRunResult]:
    """Run each account independently.

    Accounts are isolated on purpose: broker connections are per account, so one
    account halting on a broker anomaly says nothing about the next one's broker.
    Each result carries its own kill-switch reasons; deriving an exit code from
    the aggregate is the caller's job.
    """
    results: list[AccountRunResult] = []
    for account_name in account_names:
        result = _run_account_trade_loop(
            broker_factory=broker_factory,
            feature_fetchers=feature_fetchers,
            provider=provider,
            conn=conn,
            account_name=account_name,
            universe=universe,
            prices=prices,
            iv_rank_proxy=iv_rank_proxy,
            max_trades=max_trades,
            fee=fee,
            histories=histories,
        )
        results.append(result)
    return results
