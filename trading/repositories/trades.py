from __future__ import annotations

import sqlite3


def fetch_trades_for_account(conn: sqlite3.Connection, *, account_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT ticker, side, qty, price, fee, trade_time, note
        FROM trades
        WHERE account_id = ?
        ORDER BY trade_time, id
        """,
        (account_id,),
    ).fetchall()


def count_trades_between(conn: sqlite3.Connection, start_iso: str, end_iso: str) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) AS trade_count
        FROM trades
        WHERE trade_time >= ? AND trade_time <= ?
        """,
        (start_iso, end_iso),
    ).fetchone()
    return 0 if row is None else int(row["trade_count"])


def insert_trade(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    ticker: str,
    side: str,
    qty: float,
    price: float,
    fee: float,
    trade_time: str,
    note: str | None,
) -> None:
    conn.execute(
        """
        INSERT INTO trades (account_id, ticker, side, qty, price, fee, trade_time, note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            account_id,
            ticker,
            side,
            qty,
            price,
            fee,
            trade_time,
            note,
        ),
    )
    conn.commit()
