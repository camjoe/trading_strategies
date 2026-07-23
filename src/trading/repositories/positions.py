from __future__ import annotations

import sqlite3

from trading.models.books.position_record import PositionRecord
from trading.repositories.unit_of_work import commit_unit_of_work


class PositionRepository:
    """SQL access for the clean-schema positions table, keyed (book_id, symbol)."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def _row_to_record(self, row: sqlite3.Row) -> PositionRecord:
        return PositionRecord.from_mapping(dict(row))

    def upsert(
        self,
        *,
        book_id: int,
        symbol: str,
        qty: float,
        avg_cost: float,
        market_value: float,
        unrealized_pnl: float,
        updated_at: str,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO positions (
                book_id, symbol, qty, avg_cost, market_value, unrealized_pnl, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(book_id, symbol) DO UPDATE SET
                qty = excluded.qty,
                avg_cost = excluded.avg_cost,
                market_value = excluded.market_value,
                unrealized_pnl = excluded.unrealized_pnl,
                updated_at = excluded.updated_at
            """,
            (
                int(book_id),
                symbol,
                float(qty),
                float(avg_cost),
                float(market_value),
                float(unrealized_pnl),
                updated_at,
            ),
        )
        commit_unit_of_work(self._conn)

    def delete(self, *, book_id: int, symbol: str) -> None:
        self._conn.execute(
            "DELETE FROM positions WHERE book_id = ? AND symbol = ?",
            (int(book_id), symbol),
        )
        commit_unit_of_work(self._conn)

    def fetch(self, *, book_id: int, symbol: str) -> PositionRecord | None:
        row = self._conn.execute(
            "SELECT * FROM positions WHERE book_id = ? AND symbol = ?",
            (int(book_id), symbol),
        ).fetchone()
        return self._row_to_record(row) if row is not None else None

    def fetch_for_book(self, *, book_id: int) -> list[PositionRecord]:
        rows = self._conn.execute(
            "SELECT * FROM positions WHERE book_id = ? ORDER BY symbol ASC",
            (int(book_id),),
        ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def fetch_for_account(self, *, account_id: int) -> list[PositionRecord]:
        rows = self._conn.execute(
            """
            SELECT p.*
            FROM positions p
            JOIN books u ON u.id = p.book_id
            WHERE u.account_id = ?
            ORDER BY p.book_id ASC, p.symbol ASC
            """,
            (int(account_id),),
        ).fetchall()
        return [self._row_to_record(row) for row in rows]
