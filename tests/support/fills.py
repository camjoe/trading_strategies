"""Seed helper for account trade history (fills-based since revision 0006).

Account state replays ``order_fills`` + ledger cash events, so tests seed
history by creating a filled order + fill on the account's default book.
The replay applies settlement-ticker (CASH) semantics by symbol, so deposits
can be seeded as CASH buys here just like the retired trades rows.
"""

from __future__ import annotations

import sqlite3

_NOW_FALLBACK = "2026-01-01T00:00:00Z"


def ensure_default_book_id(conn: sqlite3.Connection, account_id: int, *, now: str = _NOW_FALLBACK) -> int:
    row = conn.execute(
        "SELECT id FROM books WHERE account_id = ? AND is_default = 1",
        (int(account_id),),
    ).fetchone()
    if row is not None:
        return int(row[0])
    cursor = conn.execute(
        """
        INSERT INTO books (
            account_id, name, is_default, start_equity, current_cash, current_equity,
            trade_symbols, created_at, updated_at
        )
        VALUES (?, 'default', 1, 0, 0, 0, '["AAPL","MSFT"]', ?, ?)
        """,
        (int(account_id), now, now),
    )
    return int(cursor.lastrowid)


def seed_fill_event(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    ticker: str,
    side: str,
    qty: float,
    price: float,
    fee: float = 0.0,
    trade_time: str = _NOW_FALLBACK,
) -> int:
    """Insert a filled order + fill row; returns the order id."""
    book_id = ensure_default_book_id(conn, account_id, now=trade_time)
    cursor = conn.execute(
        """
        INSERT INTO orders (
            book_id, account_id, symbol, side, qty, requested_price, status,
            filled_qty, avg_fill_price, commission, submitted_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, 'filled', ?, ?, ?, ?, ?)
        """,
        (
            book_id,
            int(account_id),
            ticker,
            side,
            float(qty),
            float(price),
            float(qty),
            float(price),
            float(fee),
            trade_time,
            trade_time,
        ),
    )
    order_id = int(cursor.lastrowid)
    conn.execute(
        """
        INSERT INTO order_fills (order_id, filled_qty, fill_price, commission, fill_time)
        VALUES (?, ?, ?, ?, ?)
        """,
        (order_id, float(qty), float(price), float(fee), trade_time),
    )
    conn.commit()
    return order_id


__all__ = ["ensure_default_book_id", "seed_fill_event"]
