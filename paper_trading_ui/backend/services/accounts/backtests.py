from __future__ import annotations

import sqlite3

from trading.backtesting.services.report_service import (
    fetch_backtest_report_summary,
    fetch_latest_backtest_run_for_account,
    fetch_latest_backtest_run_id_for_account,
    fetch_recent_backtest_runs,
)
from trading.services.accounts import find_account, is_manual_only_account_kind

from ...config import TEST_ACCOUNT_NAME, TEST_ACCOUNT_STRATEGY


def fetch_latest_backtest_summary(conn: sqlite3.Connection, account_name: str) -> dict[str, object] | None:
    run_dict = fetch_latest_backtest_run_for_account(conn, account_name=account_name)
    if run_dict is None:
        return None
    return _apply_display_names(conn, run_dict)


def _apply_display_names(conn: sqlite3.Connection, run_dict: dict[str, object]) -> dict[str, object]:
    raw_account_name = str(run_dict["accountName"])
    run_dict["accountName"] = display_account_name(conn, raw_account_name)
    run_dict["strategy"] = display_strategy(conn, raw_account_name, str(run_dict["strategy"]))
    return run_dict


def _is_manual_only_account_name(conn: sqlite3.Connection, account_name: str) -> bool:
    row = find_account(conn, account_name)
    if row is None:
        return False
    return is_manual_only_account_kind(row.account_kind)


def display_account_name(conn: sqlite3.Connection, account_name: str) -> str:
    return TEST_ACCOUNT_NAME if _is_manual_only_account_name(conn, account_name) else account_name


def display_strategy(conn: sqlite3.Connection, account_name: str, strategy: str) -> str:
    return TEST_ACCOUNT_STRATEGY if _is_manual_only_account_name(conn, account_name) else strategy


def fetch_recent_backtest_run_summaries(conn: sqlite3.Connection, *, limit: int) -> list[dict[str, object]]:
    dicts = fetch_recent_backtest_runs(conn, limit=limit)
    return [_apply_display_names(conn, d) for d in dicts]


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
