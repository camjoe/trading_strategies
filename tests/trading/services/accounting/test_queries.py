from __future__ import annotations

import sqlite3

from trading.repositories.trades import TradeRepository
from trading.services.accounting import list_account_trades


def test_list_account_trades_orders_by_trade_time_then_id(
    conn: sqlite3.Connection, accounting_account: sqlite3.Row
) -> None:
    account_id = int(accounting_account["id"])

    TradeRepository(conn).insert(
        account_id=account_id,
        ticker="MSFT",
        side="buy",
        qty=1.0,
        price=10.0,
        fee=0.0,
        trade_time="2026-01-01T00:00:01Z",
        note="second",
    )
    TradeRepository(conn).insert(
        account_id=account_id,
        ticker="AAPL",
        side="buy",
        qty=1.0,
        price=10.0,
        fee=0.0,
        trade_time="2026-01-01T00:00:00Z",
        note="first",
    )
    TradeRepository(conn).insert(
        account_id=account_id,
        ticker="GOOG",
        side="buy",
        qty=1.0,
        price=10.0,
        fee=0.0,
        trade_time="2026-01-01T00:00:01Z",
        note="third",
    )
    conn.commit()

    rows = list_account_trades(conn, account_id)
    assert [row["ticker"] for row in rows] == ["AAPL", "MSFT", "GOOG"]
