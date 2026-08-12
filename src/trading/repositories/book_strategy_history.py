from __future__ import annotations

import sqlite3

from trading.models.books import BookStrategyAssignmentRecord
from trading.persistence.unit_of_work import unit_of_work


class BookStrategyHistoryRepository:
    """SQL access for book_strategy_history.

    The book's *incumbent* is by definition its open assignment — the row with
    `effective_to IS NULL`. The one-open-assignment-per-book invariant is
    enforced by the partial unique index `idx_book_strategy_history_open_per_book`;
    `assign_strategy` closes the open row (if any) and opens the new one in a
    single transaction. (There is no `is_incumbent` flag — it was dropped in
    revision 0012 as a redundant second encoding of `effective_to IS NULL`.)
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def fetch_open(self, *, book_id: int) -> BookStrategyAssignmentRecord | None:
        row = self._conn.execute(
            "SELECT * FROM book_strategy_history WHERE book_id = ? AND effective_to IS NULL",
            (book_id,),
        ).fetchone()
        return BookStrategyAssignmentRecord.from_mapping(dict(row)) if row is not None else None

    def fetch_history(self, *, book_id: int) -> list[BookStrategyAssignmentRecord]:
        rows = self._conn.execute(
            "SELECT * FROM book_strategy_history WHERE book_id = ? ORDER BY effective_from ASC, id ASC",
            (book_id,),
        ).fetchall()
        return [BookStrategyAssignmentRecord.from_mapping(dict(row)) for row in rows]

    def assign_strategy(
        self,
        *,
        book_id: int,
        strategy_id: int,
        effective_from: str,
        created_at: str,
        updated_at: str,
    ) -> int:
        """Close the book's open assignment (if any) and open a new incumbent.

        A strategy row is its own parameterization; there is no separate
        param-set store. (The legacy ``param_set_id`` column was dropped from
        the schema in revision ``0001``.)
        """
        with unit_of_work(self._conn):
            self._conn.execute(
                """
                UPDATE book_strategy_history
                SET effective_to = ?, updated_at = ?
                WHERE book_id = ? AND effective_to IS NULL
                """,
                (effective_from, updated_at, book_id),
            )
            cursor = self._conn.execute(
                """
                INSERT INTO book_strategy_history (
                    book_id, strategy_id, effective_from, effective_to,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, NULL, ?, ?)
                """,
                (
                    book_id,
                    strategy_id,
                    effective_from,
                    created_at,
                    updated_at,
                ),
            )
        return int(cursor.lastrowid or 0)
