"""Operator-facing printed account report.

Fetches account state, evaluation evidence, and benchmark overlay from the
analysis/evaluation services and prints a single account's report. Pure
formatting helpers live in ``_formatting``; read-only computation lives in
``trading.services.analysis`` and ``trading.services.evaluation``.
"""

from __future__ import annotations

import sqlite3

from common.coercion import row_expect_int, row_float
from trading.domain.metrics.portfolio_math import alpha_pct, benchmark_available
from trading.models import AccountRecord
from trading.models.books import BookRecord
from trading.repositories.books import BookRepository
from trading.services.accounts.mutations import get_account
from trading.services.accounts.presentation import GOAL_NOT_SET_TEXT, render_account_policy_text, render_goal_text
from trading.services.analysis.portfolio import build_account_return_summary, build_account_stats
from trading.services.books.book_assignments import active_strategy_for_account
from trading.services.evaluation.queries import fetch_strategy_evaluation_for_account_row
from trading.services.market_data.protocols import MarketDataProvider
from trading.services.reporting._formatting import evaluation_summary_line


def _print_leaps_params(book: BookRecord) -> None:
    # Execution and option knobs are book columns (revisions 0004/0005).
    print(
        "LEAPs Parameters: "
        f"strike_offset_pct={book.option_strike_offset_pct} "
        f"min_dte={book.option_min_dte} max_dte={book.option_max_dte}"
    )
    print(
        "LEAPs Options Filters: "
        f"type={book.option_type} "
        f"delta={book.target_delta_min}-{book.target_delta_max} "
        f"iv_rank={book.iv_rank_min}-{book.iv_rank_max}"
    )
    print(
        "LEAPs/Options Risk Limits: "
        f"max_premium={book.max_premium_per_trade} "
        f"max_contracts={book.max_contracts_per_trade} "
        f"roll_dte={book.roll_dte_threshold} "
        f"option_profit_take_pct={book.option_profit_take_pct} "
        f"option_max_loss_pct={book.option_max_loss_pct}"
    )


def _print_account_header(conn: sqlite3.Connection, account: AccountRecord) -> None:
    active_strategy = active_strategy_for_account(conn, row_expect_int(account, "id"))
    default_book = BookRepository(conn).fetch_default_for_account(account_id=row_expect_int(account, "id"))
    print(f"Account: {account['name']}")
    print(f"Display Name: {account['descriptive_name']}")
    print(f"Account Policy: {render_account_policy_text(account, active_strategy=active_strategy, book=default_book)}")
    goal_text = render_goal_text(default_book)
    if goal_text != GOAL_NOT_SET_TEXT:
        print(f"Goal Metadata: {goal_text}")
    if default_book is not None and default_book.instrument_mode == "leaps":
        _print_leaps_params(default_book)


def _print_performance_lines(
    account: AccountRecord,
    cash: float,
    market_value: float,
    equity: float,
    realized_pnl: float,
    unrealized: float,
    strategy_return_pct_value: float,
    benchmark_equity: float | None,
    benchmark_return_pct: float | None,
) -> None:
    initial_cash = row_float(account, "initial_cash")
    print(f"Initial Cash: {initial_cash:.2f}" if initial_cash is not None else "Initial Cash: N/A")
    print(f"Cash: {cash:.2f}")
    print(f"Market Value: {market_value:.2f}")
    print(f"Equity: {equity:.2f}")
    print(f"Account Return %: {strategy_return_pct_value:.2f}")
    print(f"Realized PnL: {realized_pnl:.2f}")
    print(f"Unrealized PnL: {unrealized:.2f}")

    if benchmark_available(benchmark_equity, benchmark_return_pct):
        assert benchmark_return_pct is not None
        assert benchmark_equity is not None
        alpha_value = alpha_pct(strategy_return_pct_value, benchmark_return_pct)
        print(f"Benchmark Equity: {benchmark_equity:.2f}")
        print(f"Benchmark Return %: {benchmark_return_pct:.2f}")
        print(f"Account Alpha vs Benchmark %: {alpha_value:.2f}")
        return

    print("Benchmark comparison: unavailable (price history not found)")


def _print_open_positions(
    positions: dict[str, float],
    avg_cost: dict[str, float],
    prices: dict[str, float],
) -> None:
    if not positions:
        print("Open Positions: none")
        return

    print("Open Positions:")
    for ticker in sorted(positions.keys()):
        qty = positions[ticker]
        avg = avg_cost.get(ticker, 0.0)
        px = prices.get(ticker)
        px_display = f"{px:.2f}" if px is not None else "N/A"
        print(f"- {ticker}: qty={qty:.4f}, avg_cost={avg:.2f}, last_price={px_display}")


def account_report(
    conn: sqlite3.Connection,
    account_name: str,
    *,
    provider: MarketDataProvider | None = None,
) -> tuple[dict[str, float], dict[str, float]]:
    account = get_account(conn, account_name)
    state, prices, market_value, unrealized, equity = build_account_stats(conn, account, provider=provider)
    evaluation = fetch_strategy_evaluation_for_account_row(conn, account)
    summary = build_account_return_summary(account, state, equity, provider=provider)
    strategy_return_pct_value = summary.account_return_pct

    _print_account_header(conn, account)
    _print_performance_lines(
        account,
        state.cash,
        market_value,
        equity,
        state.realized_pnl,
        unrealized,
        strategy_return_pct_value,
        summary.benchmark_equity,
        summary.benchmark_return_pct,
    )
    print(evaluation_summary_line(evaluation, prefix="Evaluation Summary: "))
    _print_open_positions(state.positions, state.avg_cost, prices)

    stats = {
        "cash": state.cash,
        "market_value": market_value,
        "equity": equity,
        "realized_pnl": state.realized_pnl,
        "unrealized_pnl": unrealized,
        "strategy_return_pct": strategy_return_pct_value,
    }
    return stats, state.positions


__all__ = ["account_report"]
