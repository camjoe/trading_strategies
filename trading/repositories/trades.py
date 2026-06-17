from __future__ import annotations

import sqlite3


class TradeRepository:

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def fetch_for_account(self, *, account_id: int) -> list[sqlite3.Row]:
        return self._conn.execute(
            """
            SELECT ticker, side, qty, price, fee, trade_time, note
            FROM trades
            WHERE account_id = ?
            ORDER BY trade_time, id
            """,
            (account_id,),
        ).fetchall()

    def fetch_count_between(self, *, start_iso: str, end_iso: str) -> int:
        row = self._conn.execute(
            """
            SELECT COUNT(*) AS trade_count
            FROM trades
            WHERE trade_time >= ? AND trade_time <= ?
            """,
            (start_iso, end_iso),
        ).fetchone()
        return 0 if row is None else int(row["trade_count"])

    def insert(
        self,
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
        self._conn.execute(
            """
            INSERT INTO trades (account_id, ticker, side, qty, price, fee, trade_time, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (account_id, ticker, side, qty, price, fee, trade_time, note),
        )
        self._conn.commit()
