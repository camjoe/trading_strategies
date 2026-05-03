from __future__ import annotations

import sqlite3

from trading.backtesting.services.report_service import (
    fetch_backtest_report_summary,
    fetch_latest_backtest_run_for_account,
    fetch_latest_backtest_run_id_for_account,
    fetch_recent_backtest_runs,
)


def fetch_latest_backtest_summary(conn: sqlite3.Connection, account_name: str) -> dict[str, object] | None:
    return fetch_latest_backtest_run_for_account(conn, account_name=account_name)


def fetch_recent_backtest_run_summaries(conn: sqlite3.Connection, *, limit: int) -> list[dict[str, object]]:
    return fetch_recent_backtest_runs(conn, limit=limit)


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
