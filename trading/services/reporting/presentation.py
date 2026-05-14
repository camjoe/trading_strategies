"""Reporting presentation/orchestration helpers for operator-facing consumers.

Owns report printing, comparisons, and snapshot capture beneath the stable
``trading.services.reporting`` package surface.
"""

from __future__ import annotations

import sqlite3

from common.coercion import row_expect_float, row_expect_str, row_float
from common.time import utc_now_iso
from trading.domain.evaluation_models import StrategyEvaluationArtifact
from trading.models import AccountRecord
from trading.repositories.snapshots import insert_snapshot_row
from trading.services.accounts import (
    GOAL_NOT_SET_TEXT,
    format_account_policy_text,
    format_goal_text,
    get_account,
    list_account_records,
    list_account_snapshots,
)
from trading.services.evaluation import fetch_strategy_evaluation_for_account_row
from trading.services.reporting.calculations import (
    alpha_pct,
    benchmark_available,
    positions_summary_text,
    strategy_return_pct,
)
from trading.services.pricing import benchmark_stats
from trading.services.reporting.stats import build_account_stats, infer_overall_trend


def _print_leaps_params(account: AccountRecord) -> None:
    print(
        "LEAPs Parameters: "
        f"strike_offset_pct={account['option_strike_offset_pct']} "
        f"min_dte={account['option_min_dte']} max_dte={account['option_max_dte']}"
    )
    print(
        "LEAPs Options Filters: "
        f"type={account['option_type']} "
        f"delta={account['target_delta_min']}-{account['target_delta_max']} "
        f"iv_rank={account['iv_rank_min']}-{account['iv_rank_max']}"
    )
    print(
        "LEAPs/Options Risk Limits: "
        f"max_premium={account['max_premium_per_trade']} "
        f"max_contracts={account['max_contracts_per_trade']} "
        f"roll_dte={account['roll_dte_threshold']} "
        f"leaps_profit_take_pct={account['profit_take_pct']} "
        f"leaps_max_loss_pct={account['max_loss_pct']}"
    )


def _print_account_header(account: AccountRecord) -> None:
    print(f"Account: {account['name']}")
    print(f"Display Name: {account['descriptive_name']}")
    print(f"Account Policy: {format_account_policy_text(account)}")
    goal_text = format_goal_text(account)
    if goal_text != GOAL_NOT_SET_TEXT:
        print(f"Goal Metadata: {goal_text}")
    if account["instrument_mode"] == "leaps":
        _print_leaps_params(account)


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


def _compare_account_header(account: AccountRecord) -> str:
    return f"- {account['name']} | display_name={account['descriptive_name']}"


def _compare_goal_metadata_line(account: AccountRecord) -> str | None:
    goal_text = format_goal_text(account)
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


def _format_percentage_or_na(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.2f}%"


def _format_backtest_evidence_summary(evaluation: StrategyEvaluationArtifact) -> str:
    if not evaluation.backtest.available:
        return "backtest=N/A"
    return (
        f"backtest={_format_percentage_or_na(evaluation.backtest.total_return_pct)} "
        f"({evaluation.backtest.trade_count or 0} trades)"
    )


def _format_paper_live_evidence_summary(evaluation: StrategyEvaluationArtifact) -> str:
    label = evaluation.paper_live.mode or "paper_live"
    if not evaluation.paper_live.available:
        return f"{label}=N/A"
    return (
        f"{label}={_format_percentage_or_na(evaluation.paper_live.return_pct)} "
        f"({evaluation.paper_live.snapshot_count or 0} snapshots)"
    )


def _evaluation_summary_line(
    evaluation: StrategyEvaluationArtifact,
    *,
    prefix: str,
) -> str:
    return (
        f"{prefix}{_format_backtest_evidence_summary(evaluation)} | "
        f"{_format_paper_live_evidence_summary(evaluation)} | "
        f"blended_score={_format_percentage_or_na(evaluation.confidence.blended_score)} | "
        f"confidence={evaluation.confidence.overall_confidence:.2f}"
    )


def account_report(conn: sqlite3.Connection, account_name: str) -> tuple[dict[str, float], dict[str, float]]:
    account = get_account(conn, account_name)
    state, prices, market_value, unrealized, equity = build_account_stats(conn, account)
    evaluation = fetch_strategy_evaluation_for_account_row(conn, account)
    benchmark_ticker = row_expect_str(account, "benchmark_ticker")
    initial_cash = row_expect_float(account, "initial_cash")
    created_at = row_expect_str(account, "created_at")
    effective_initial = initial_cash if initial_cash else state.total_deposited
    benchmark_equity, benchmark_return_pct = benchmark_stats(benchmark_ticker, effective_initial, created_at)
    strategy_return_pct_value = strategy_return_pct(equity, effective_initial) if effective_initial else 0.0

    _print_account_header(account)
    _print_performance_lines(
        account,
        state.cash,
        market_value,
        equity,
        state.realized_pnl,
        unrealized,
        strategy_return_pct_value,
        benchmark_equity,
        benchmark_return_pct,
    )
    print(_evaluation_summary_line(evaluation, prefix="Evaluation Summary: "))
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


def compare_strategies(conn: sqlite3.Connection, lookback: int) -> None:
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
        state, _prices, _market_value, _unrealized, equity = build_account_stats(conn, account)
        evaluation = fetch_strategy_evaluation_for_account_row(conn, account)
        initial_cash = account.initial_cash
        if not initial_cash:
            continue
        benchmark_ticker = account.benchmark_ticker
        created_at = account.created_at
        account_id = account.id
        strategy_return_pct_value = strategy_return_pct(equity, initial_cash)
        bench_equity, bench_return_pct = benchmark_stats(benchmark_ticker, initial_cash, created_at)
        trend = infer_overall_trend(conn, account_id, equity, lookback)

        position_count, positions_text = positions_summary_text(state.positions)

        print(_compare_account_header(account))
        print(f"  account_policy={format_account_policy_text(account)}")
        goal_metadata_line = _compare_goal_metadata_line(account)
        if goal_metadata_line is not None:
            print(goal_metadata_line)
        print(
            f"  equity={equity:.2f} account_return={strategy_return_pct_value:.2f}% "
            f"positions={position_count} trend={trend}"
        )
        print(_compare_benchmark_line(strategy_return_pct_value, bench_equity, bench_return_pct))
        print(_evaluation_summary_line(evaluation, prefix="  "))
        print(f"  positions: {positions_text}")


def snapshot_account(conn: sqlite3.Connection, account_name: str, snapshot_time: str | None) -> None:
    account = get_account(conn, account_name)
    stats, _ = account_report(conn, account_name)
    insert_snapshot_row(
        conn,
        account_id=account.id,
        snapshot_time=snapshot_time or utc_now_iso(),
        cash=stats["cash"],
        market_value=stats["market_value"],
        equity=stats["equity"],
        realized_pnl=stats["realized_pnl"],
        unrealized_pnl=stats["unrealized_pnl"],
    )
    print("Snapshot saved.")


def show_snapshots(conn: sqlite3.Connection, account_name: str, limit: int) -> None:
    account = get_account(conn, account_name)
    rows = list_account_snapshots(conn, account.id, limit=int(limit))

    if not rows:
        print("No snapshots found.")
        return

    print(f"Snapshot history (latest {limit}) for {account_name}:")
    for row in rows:
        print(
            f"- {row['snapshot_time']} | equity={row['equity']:.2f} cash={row['cash']:.2f} "
            f"mv={row['market_value']:.2f} realized={row['realized_pnl']:.2f} "
            f"unrealized={row['unrealized_pnl']:.2f}"
        )


__all__ = [
    "account_report",
    "compare_strategies",
    "show_snapshots",
    "snapshot_account",
]
