from __future__ import annotations

import sqlite3

from tests.support.fills import seed_fill_event
from trading.services.accounting import list_account_trades


def test_list_account_trades_orders_by_trade_time_then_id(
    conn: sqlite3.Connection, accounting_account: sqlite3.Row
) -> None:
    account_id = int(accounting_account["id"])

    seed_fill_event(
        conn,
        account_id=account_id,
        ticker="MSFT",
        side="buy",
        qty=1.0,
        price=10.0,
        trade_time="2026-01-01T00:00:01Z",
    )
    seed_fill_event(
        conn,
        account_id=account_id,
        ticker="AAPL",
        side="buy",
        qty=1.0,
        price=10.0,
        trade_time="2026-01-01T00:00:00Z",
    )
    seed_fill_event(
        conn,
        account_id=account_id,
        ticker="GOOG",
        side="buy",
        qty=1.0,
        price=10.0,
        trade_time="2026-01-01T00:00:01Z",
    )

    rows = list_account_trades(conn, account_id)
    assert [row["ticker"] for row in rows] == ["AAPL", "MSFT", "GOOG"]


def test_list_account_trades_includes_ledger_cash_events(
    conn: sqlite3.Connection, accounting_account: sqlite3.Row
) -> None:
    account_id = int(accounting_account["id"])
    seed_fill_event(
        conn,
        account_id=account_id,
        ticker="AAPL",
        side="buy",
        qty=1.0,
        price=10.0,
        trade_time="2026-01-02T00:00:00Z",
    )
    book_row = conn.execute("SELECT id FROM books WHERE account_id = ? AND is_default = 1", (account_id,)).fetchone()
    conn.execute(
        """
        INSERT INTO ledger (book_id, entry_type, amount, entry_time, created_at)
        VALUES (?, 'deposit', 500.0, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')
        """,
        (int(book_row[0]),),
    )
    conn.commit()

    rows = list_account_trades(conn, account_id)
    assert [(row["ticker"], row["side"]) for row in rows] == [("CASH", "buy"), ("AAPL", "buy")]
    assert float(rows[0]["qty"]) == 500.0
