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
    run_dict = fetch_latest_backtest_run_for_account(conn, account_name=account_name)
    if run_dict is None:
        return None
    return _apply_display_names(run_dict)


def _apply_display_names(run_dict: dict[str, object]) -> dict[str, object]:
    raw_account_name = str(run_dict["accountName"])
    run_dict["accountName"] = display_account_name(raw_account_name)
    run_dict["strategy"] = display_strategy(raw_account_name, str(run_dict["strategy"]))
    return run_dict


def display_account_name(account_name: str) -> str:
    return TEST_ACCOUNT_NAME if account_name == TEST_BACKTEST_ACCOUNT_NAME else account_name


def display_strategy(account_name: str, strategy: str) -> str:
    return TEST_ACCOUNT_STRATEGY if account_name == TEST_BACKTEST_ACCOUNT_NAME else strategy


def fetch_recent_backtest_run_summaries(conn: sqlite3.Connection, *, limit: int) -> list[dict[str, object]]:
    dicts = fetch_recent_backtest_runs(conn, limit=limit)
    return [_apply_display_names(d) for d in dicts]


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
