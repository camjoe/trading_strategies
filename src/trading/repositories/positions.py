from __future__ import annotations

import sqlite3

from trading.models.books import PositionRecord
from trading.persistence.unit_of_work import commit_unit_of_work


class PositionRepository:
    """SQL access for the clean-schema positions table, keyed (book_id, symbol)."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

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
                book_id,
                symbol,
                qty,
                avg_cost,
                market_value,
                unrealized_pnl,
                updated_at,
            ),
        )
        commit_unit_of_work(self._conn)

    def delete(self, *, book_id: int, symbol: str) -> None:
        self._conn.execute(
            "DELETE FROM positions WHERE book_id = ? AND symbol = ?",
            (book_id, symbol),
        )
        commit_unit_of_work(self._conn)

    def _fetch(self, filter_sql: str, params: tuple[object, ...]) -> list[PositionRecord]:
        rows = self._conn.execute(f"SELECT p.* FROM positions p {filter_sql}", params).fetchall()
        return [PositionRecord.from_mapping(dict(row)) for row in rows]

    def fetch(self, *, book_id: int, symbol: str) -> PositionRecord | None:
        found = self._fetch("WHERE p.book_id = ? AND p.symbol = ?", (book_id, symbol))
        return found[0] if found else None

    def fetch_for_book(self, *, book_id: int) -> list[PositionRecord]:
        return self._fetch("WHERE p.book_id = ? ORDER BY p.symbol ASC", (book_id,))

    def fetch_for_account(self, *, account_id: int) -> list[PositionRecord]:
        return self._fetch(
            "JOIN books b ON b.id = p.book_id WHERE b.account_id = ? ORDER BY p.book_id ASC, p.symbol ASC",
            (account_id,),
        )
