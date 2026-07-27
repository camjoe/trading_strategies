from __future__ import annotations

import sqlite3

from common.coercion import coerce_int
from trading.models import AccountRecord
from trading.models.portfolio.equity_snapshot_record import EquitySnapshotRecord
from trading.services.accounts import (
    get_account,
    list_account_records,
)


def require_account_row(conn: sqlite3.Connection, account_name: str) -> AccountRecord:
    # get_account raises NotFoundError, mapped to HTTP 404 by the app-level handler.
    return get_account(conn, account_name)


def fetch_visible_account_rows(conn: sqlite3.Connection) -> list[AccountRecord]:
    return list_account_records(conn)


def build_snapshot_payload(snapshot: EquitySnapshotRecord) -> dict[str, object]:
    return {
        "time": snapshot.snapshot_time,
        "cash": snapshot.cash,
        "marketValue": snapshot.market_value,
        "equity": snapshot.equity,
        "realizedPnl": snapshot.realized_pnl,
        "unrealizedPnl": snapshot.unrealized_pnl,
    }


def build_trade_payload(
    trade: dict[str, object],
    *,
    book_names: dict[int, str] | None = None,
) -> dict[str, object]:
    book_id = coerce_int(trade.get("book_id"))
    return {
        "bookId": book_id,
        "bookName": book_names.get(book_id) if book_names is not None and book_id is not None else None,
        "ticker": trade["ticker"],
        "side": trade["side"],
        "qty": trade["qty"],
        "price": trade["price"],
        "fee": trade["fee"],
        "tradeTime": trade["trade_time"],
        "note": trade["note"],
    }
