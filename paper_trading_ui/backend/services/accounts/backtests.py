from __future__ import annotations

import sqlite3

from trading.backtesting.services.report_service import (
    fetch_backtest_report_summary,
    fetch_latest_backtest_run_for_account,
    fetch_latest_backtest_run_id_for_account,
    fetch_recent_backtest_runs,
)

from ...config import TEST_ACCOUNT_NAME, TEST_ACCOUNT_STRATEGY, TEST_BACKTEST_ACCOUNT_NAME


def fetch_latest_backtest_summary(conn: sqlite3.Connection, account_name: str) -> dict[str, object] | None:
    row = fetch_latest_backtest_run_for_account(conn, account_name=account_name)
    if row is None:
        return None
    return build_backtest_run_summary(row)


def build_backtest_run_summary(row: sqlite3.Row) -> dict[str, object]:
    account_name = str(row["account_name"])
    account_display_name = display_account_name(account_name)
    strategy_display_name = display_strategy(account_name, str(row["strategy"]))

    return {
        "runId": int(row["id"]),
        "runName": row["run_name"],
        "accountName": account_display_name,
        "strategy": strategy_display_name,
        "startDate": row["start_date"],
        "endDate": row["end_date"],
        "createdAt": row["created_at"],
        "slippageBps": float(row["slippage_bps"]),
        "feePerTrade": float(row["fee_per_trade"]),
        "tickersFile": row["tickers_file"],
    }


def display_account_name(account_name: str) -> str:
    return TEST_ACCOUNT_NAME if account_name == TEST_BACKTEST_ACCOUNT_NAME else account_name


def display_strategy(account_name: str, strategy: str) -> str:
    return TEST_ACCOUNT_STRATEGY if account_name == TEST_BACKTEST_ACCOUNT_NAME else strategy


def fetch_recent_backtest_run_summaries(conn: sqlite3.Connection, *, limit: int) -> list[dict[str, object]]:
    rows = fetch_recent_backtest_runs(conn, limit=limit)
    return [build_backtest_run_summary(row) for row in rows]


def fetch_latest_backtest_metrics(conn: sqlite3.Connection, account_name: str) -> dict[str, object] | None:
    latest_run_id = fetch_latest_backtest_run_id_for_account(conn, account_name=account_name)
    if latest_run_id is None:
        return None

    try:
        report = fetch_backtest_report_summary(conn, int(latest_run_id))
    except ValueError:
        return None
    return {
        "runId": report.run_id,
        "endDate": report.end_date,
        "totalReturnPct": report.total_return_pct,
        "maxDrawdownPct": report.max_drawdown_pct,
        "sharpeRatio": report.sharpe_ratio,
        "sortinoRatio": report.sortino_ratio,
        "calmarRatio": report.calmar_ratio,
        "winRatePct": report.win_rate_pct,
        "profitFactor": report.profit_factor,
        "avgTradeReturnPct": report.avg_trade_return_pct,
    }
