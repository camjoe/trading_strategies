from __future__ import annotations

import sqlite3

from trading.services.accounts_service import (
    fetch_account_rows_excluding,
    fetch_all_account_names,
    fetch_snapshot_history_rows,
)

from ...config import TEST_BACKTEST_ACCOUNT_NAME


def fetch_managed_account_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return fetch_account_rows_excluding(conn, excluded_name=TEST_BACKTEST_ACCOUNT_NAME)


def fetch_account_names(conn: sqlite3.Connection) -> list[str]:
    return fetch_all_account_names(conn)


def fetch_account_snapshot_rows(
    conn: sqlite3.Connection, account_id: int, *, limit: int = 100
) -> list[sqlite3.Row]:
    return fetch_snapshot_history_rows(conn, account_id=account_id, limit=limit)


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
        "note": trade["note"],
    }


def fetch_account_trades(conn: sqlite3.Connection, account_id: int) -> list[sqlite3.Row]:
    from trading.services.reporting_service import load_account_trades

    return load_account_trades(conn, account_id)


def take_snapshot(conn: sqlite3.Connection, account_name: str, *, snapshot_time: str | None = None) -> None:
    from trading.services.reporting_service import take_account_snapshot

    take_account_snapshot(conn, account_name, snapshot_time=snapshot_time)
