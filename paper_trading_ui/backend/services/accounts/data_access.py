from __future__ import annotations

import sqlite3

from trading.models import AccountRecord
from trading.services.accounts_service import (
    ACCOUNT_KIND_LOCAL,
    ACCOUNT_KIND_MANAGED,
    list_account_records,
    list_account_snapshots as _list_account_snapshots,
)
from trading.services.accounting_service import load_trades
from trading.services.reporting_service import snapshot_account


VISIBLE_ACCOUNT_KINDS = (ACCOUNT_KIND_MANAGED, ACCOUNT_KIND_LOCAL)


def fetch_visible_account_rows(conn: sqlite3.Connection) -> list[AccountRecord]:
    return list_account_records(conn, account_kinds=VISIBLE_ACCOUNT_KINDS)


def build_snapshot_payload(snapshot: dict[str, object]) -> dict[str, object]:
    return {
        "time": snapshot["snapshot_time"],
        "cash": snapshot["cash"],
        "marketValue": snapshot["market_value"],
        "equity": snapshot["equity"],
        "realizedPnl": snapshot["realized_pnl"],
        "unrealizedPnl": snapshot["unrealized_pnl"],
    }


def build_trade_payload(trade: dict[str, object]) -> dict[str, object]:
    return {
        "ticker": trade["ticker"],
        "side": trade["side"],
        "qty": trade["qty"],
        "price": trade["price"],
        "fee": trade["fee"],
        "tradeTime": trade["trade_time"],
        "note": trade["note"],
    }


def fetch_account_trades(conn: sqlite3.Connection, account_id: int) -> list[dict[str, object]]:
    return load_trades(conn, account_id)


def take_snapshot(conn: sqlite3.Connection, account_name: str, *, snapshot_time: str | None = None) -> None:
    snapshot_account(conn, account_name, snapshot_time)


def fetch_snapshot_history_rows(conn: sqlite3.Connection, account_id: int, *, limit: int) -> list[dict[str, object]]:
    return _list_account_snapshots(conn, account_id, limit=limit)
