from __future__ import annotations

import sqlite3

from trading.services.accounts_service import (
    fetch_account_rows_excluding,
    fetch_snapshot_history_rows as _fetch_snapshot_history_rows,
)
from trading.services.accounting_service import load_trades
from trading.services.reporting_service import snapshot_account

from ...config import TEST_BACKTEST_ACCOUNT_NAME


def fetch_managed_account_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return fetch_account_rows_excluding(conn, excluded_name=TEST_BACKTEST_ACCOUNT_NAME)


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
    return load_trades(conn, account_id)


def take_snapshot(conn: sqlite3.Connection, account_name: str, *, snapshot_time: str | None = None) -> None:
    snapshot_account(conn, account_name, snapshot_time)


def fetch_snapshot_history_rows(conn: sqlite3.Connection, account_id: int, *, limit: int) -> list[sqlite3.Row]:
    return _fetch_snapshot_history_rows(conn, account_id, limit=limit)
