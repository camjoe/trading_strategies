from __future__ import annotations

import sqlite3

from trading.backtesting.services.report_service import (
    fetch_backtest_report_summary,
    fetch_latest_backtest_run_for_account,
    fetch_latest_backtest_run_id_for_account,
    fetch_recent_backtest_runs,
)
from trading.services.accounts_service import (
    fetch_account_rows_excluding,
    fetch_all_account_names,
    fetch_snapshot_history_rows,
    update_account_fields_by_id,
)
from trading.services.reporting_service import get_account_stats as build_account_stats

from ..config import TEST_ACCOUNT_NAME, TEST_ACCOUNT_STRATEGY, TEST_BACKTEST_ACCOUNT_NAME
from .db import fetch_latest_snapshot_row


def build_account_summary(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, object]:
    _state, _prices, _mv, _unrealized, equity = build_account_stats(conn, row)
    latest_snapshot = fetch_latest_snapshot_row(conn, int(row["id"]))

    initial_cash = float(row["initial_cash"])
    delta = equity - initial_cash
    delta_pct = ((equity / initial_cash) - 1.0) * 100.0 if initial_cash else 0.0

    change_since_snapshot = None
    if latest_snapshot is not None:
        previous_equity = float(latest_snapshot["equity"])
        change_since_snapshot = equity - previous_equity

    return {
        "name": row["name"],
        "displayName": row["descriptive_name"],
        "strategy": row["strategy"],
        "instrumentMode": row["instrument_mode"],
        "riskPolicy": row["risk_policy"],
        "benchmark": row["benchmark_ticker"],
        "initialCash": initial_cash,
        "equity": equity,
        "totalChange": delta,
        "totalChangePct": delta_pct,
        "changeSinceLastSnapshot": change_since_snapshot,
        "latestSnapshotTime": latest_snapshot["snapshot_time"] if latest_snapshot else None,
    }


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


def fetch_managed_account_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return fetch_account_rows_excluding(conn, excluded_name=TEST_BACKTEST_ACCOUNT_NAME)


def fetch_account_names(conn: sqlite3.Connection) -> list[str]:
    return fetch_all_account_names(conn)


def fetch_account_snapshot_rows(conn: sqlite3.Connection, account_id: int, *, limit: int = 100) -> list[sqlite3.Row]:
    return fetch_snapshot_history_rows(conn, account_id=account_id, limit=limit)


def fetch_recent_backtest_run_summaries(conn: sqlite3.Connection, *, limit: int) -> list[dict[str, object]]:
    rows = fetch_recent_backtest_runs(conn, limit=limit)
    return [build_backtest_run_summary(row) for row in rows]


def build_comparison_account_payload(
    summary: dict[str, object],
    latest_backtest: dict[str, object] | None,
) -> dict[str, object]:
    return {
        "name": summary["name"],
        "displayName": summary["displayName"],
        "strategy": summary["strategy"],
        "benchmark": summary["benchmark"],
        "equity": summary["equity"],
        "initialCash": summary["initialCash"],
        "totalChange": summary["totalChange"],
        "totalChangePct": summary["totalChangePct"],
        "latestBacktest": latest_backtest,
    }


def build_snapshot_payload(snapshot: sqlite3.Row) -> dict[str, object]:
    return {
        "time": snapshot["snapshot_time"],
        "cash": float(snapshot["cash"]),
        "marketValue": float(snapshot["market_value"]),
        "equity": float(snapshot["equity"]),
        "realizedPnl": float(snapshot["realized_pnl"]),
        "unrealizedPnl": float(snapshot["unrealized_pnl"]),
    }


def build_trade_payload(trade: sqlite3.Row) -> dict[str, object]:
    return {
        "ticker": trade["ticker"],
        "side": trade["side"],
        "qty": float(trade["qty"]),
        "price": float(trade["price"]),
        "fee": float(trade["fee"]),
        "tradeTime": trade["trade_time"],
    }


def fetch_latest_backtest_metrics(conn: sqlite3.Connection, account_name: str) -> dict[str, object] | None:
    latest_run_id = fetch_latest_backtest_run_id_for_account(conn, account_name=account_name)
    if latest_run_id is None:
        return None

    report = fetch_backtest_report_summary(conn, int(latest_run_id))
    return {
        "runId": report.run_id,
        "endDate": report.end_date,
        "totalReturnPct": report.total_return_pct,
        "maxDrawdownPct": report.max_drawdown_pct,
        "alphaPct": None,
    }


def fetch_account_trades(conn: sqlite3.Connection, account_id: int) -> list[sqlite3.Row]:
    from trading.services.reporting_service import load_account_trades
    return load_account_trades(conn, account_id)


def take_snapshot(conn: sqlite3.Connection, account_name: str, *, snapshot_time: str | None = None) -> None:
    from trading.services.reporting_service import take_account_snapshot
    take_account_snapshot(conn, account_name, snapshot_time=snapshot_time)


def update_account_params(
    conn: sqlite3.Connection,
    account_id: int,
    *,
    strategy: str | None = None,
    risk_policy: str | None = None,
) -> None:
    """Partial-update strategy and/or risk_policy for the given account."""
    updates: list[str] = []
    params: list[object] = []
    if strategy is not None:
        updates.append("strategy = ?")
        params.append(strategy)
    if risk_policy is not None:
        updates.append("risk_policy = ?")
        params.append(risk_policy)
    if updates:
        update_account_fields_by_id(conn, account_id, updates=updates, params=params)

