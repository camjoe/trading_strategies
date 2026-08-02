"""Operator-facing printed comparison of paper accounts.

Prints each account's current policy, holdings state, benchmark overlay, and
evaluation evidence. Pure formatting helpers live in ``_formatting``; read-only
computation lives in ``trading.services.analysis`` and
``trading.services.evaluation``.
"""

from __future__ import annotations

import sqlite3

from trading.domain.portfolio_math import alpha_pct, benchmark_available, strategy_return_pct
from trading.models import AccountRecord
from trading.models.books import BookRecord
from trading.repositories.books import BookRepository
from trading.services.accounts import (
    GOAL_NOT_SET_TEXT,
    format_account_policy_text,
    format_goal_text,
    list_account_records,
)
from trading.services.analysis.portfolio import build_account_stats, infer_overall_trend
from trading.services.books.book_assignments import active_strategy_for_account
from trading.services.evaluation import fetch_strategy_evaluation_for_account_row
from trading.services.market_data import MarketDataProvider
from trading.services.market_data.lookups import benchmark_stats
from trading.services.reporting._formatting import evaluation_summary_line, positions_summary_text


def _compare_account_header(account: AccountRecord) -> str:
    return f"- {account['name']} | display_name={account['descriptive_name']}"


def _compare_goal_metadata_line(book: BookRecord | None) -> str | None:
    goal_text = format_goal_text(book)
    if goal_text == GOAL_NOT_SET_TEXT:
        return None
    return f"  goal_metadata={goal_text}"


def _compare_benchmark_line(
    strategy_return_pct_value: float,
    benchmark_equity: float | None,
    benchmark_return_pct: float | None,
) -> str:
    if benchmark_available(benchmark_equity, benchmark_return_pct):
        assert benchmark_equity is not None
        assert benchmark_return_pct is not None
        alpha_value = alpha_pct(strategy_return_pct_value, benchmark_return_pct)
        return (
            f"  benchmark_equity={benchmark_equity:.2f} benchmark_return={benchmark_return_pct:.2f}% "
            f"account_alpha={alpha_value:.2f}%"
        )
    return "  benchmark_equity=N/A benchmark_return=N/A account_alpha=N/A"


def compare_strategies(
    conn: sqlite3.Connection,
    lookback: int,
    *,
    provider: MarketDataProvider | None = None,
) -> None:
    accounts = list_account_records(conn)

    if not accounts:
        print("No paper accounts found.")
        return

    print("Account policy comparison (current paper account state):")
    print(
        "Compares each account's current policy and holdings state, with canonical evaluation evidence "
        "summaries when available."
    )
    for account in accounts:
        state, _prices, _market_value, _unrealized, equity = build_account_stats(conn, account, provider=provider)
        evaluation = fetch_strategy_evaluation_for_account_row(conn, account)
        initial_cash = account.initial_cash
        if not initial_cash:
            continue
        benchmark_ticker = account.benchmark_ticker
        created_at = account.created_at
        account_id = account.id
        strategy_return_pct_value = strategy_return_pct(equity, initial_cash)
        bench_equity, bench_return_pct = benchmark_stats(benchmark_ticker, initial_cash, created_at, provider=provider)
        trend = infer_overall_trend(conn, account_id, equity, lookback)

        position_count, positions_text = positions_summary_text(state.positions)

        print(_compare_account_header(account))
        active_strategy = active_strategy_for_account(conn, account.id)
        compare_book = BookRepository(conn).fetch_default_for_account(account_id=account.id)
        print(
            "  account_policy="
            f"{format_account_policy_text(account, active_strategy=active_strategy, book=compare_book)}"
        )
        goal_metadata_line = _compare_goal_metadata_line(compare_book)
        if goal_metadata_line is not None:
            print(goal_metadata_line)
        print(
            f"  equity={equity:.2f} account_return={strategy_return_pct_value:.2f}% "
            f"positions={position_count} trend={trend}"
        )
        print(_compare_benchmark_line(strategy_return_pct_value, bench_equity, bench_return_pct))
        print(evaluation_summary_line(evaluation, prefix="  "))
        print(f"  positions: {positions_text}")


__all__ = ["compare_strategies"]
