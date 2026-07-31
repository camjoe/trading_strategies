"""Auto-trading input and batch orchestration helpers."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Mapping

import pandas as pd

from common.tickers import load_tickers_from_file
from trading.domain.broker_connection import BrokerConnection
from trading.domain.feature_provider import FeatureFetcherSet
from trading.models import AccountRecord
from trading.services.auto_trading.market import build_iv_rank_proxy, fetch_bar_histories
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


def resolve_market_inputs(
    tickers_file: str,
    *,
    provider: MarketDataProvider | None = None,
) -> tuple[list[str], dict[str, float], dict[str, float], dict[str, pd.DataFrame]]:
    universe = load_tickers_from_file(tickers_file)
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
) -> int:
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
) -> list[tuple[str, int]]:
    results: list[tuple[str, int]] = []
    for account_name in account_names:
        executed = _run_account_trade_loop(
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
        results.append((account_name, executed))
    return results
