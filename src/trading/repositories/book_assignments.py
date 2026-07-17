from __future__ import annotations

import sqlite3

from trading.models.books.book_strategy_assignment_record import BookStrategyAssignmentRecord


class BookAssignmentRepository:
    """SQL access for book_strategy_assignments.

    The one-open-assignment-per-book invariant is enforced by the partial unique
    index `idx_book_assignments_open_per_book`; `assign_strategy` closes the open
    row (if any) and opens the new one in a single transaction.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def _row_to_record(self, row: sqlite3.Row) -> BookStrategyAssignmentRecord:
        return BookStrategyAssignmentRecord.from_mapping(dict(row))

    def fetch_open(self, *, book_id: int) -> BookStrategyAssignmentRecord | None:
        row = self._conn.execute(
            "SELECT * FROM book_strategy_assignments WHERE book_id = ? AND effective_to IS NULL",
            (int(book_id),),
        ).fetchone()
        return self._row_to_record(row) if row is not None else None

    def fetch_history(self, *, book_id: int) -> list[BookStrategyAssignmentRecord]:
        rows = self._conn.execute(
            "SELECT * FROM book_strategy_assignments WHERE book_id = ? ORDER BY effective_from ASC, id ASC",
            (int(book_id),),
        ).fetchall()
        return [self._row_to_record(row) for row in rows]

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
        try:
            self._conn.execute(
                """
                UPDATE book_strategy_assignments
                SET effective_to = ?, is_incumbent = 0, updated_at = ?
                WHERE book_id = ? AND effective_to IS NULL
                """,
                (effective_from, updated_at, int(book_id)),
            )
            cursor = self._conn.execute(
                """
                INSERT INTO book_strategy_assignments (
                    book_id, strategy_id, effective_from, effective_to,
                    is_incumbent, created_at, updated_at
                )
                VALUES (?, ?, ?, NULL, 1, ?, ?)
                """,
                (
                    int(book_id),
                    int(strategy_id),
                    effective_from,
                    created_at,
                    updated_at,
                ),
            )
        except Exception:
            self._conn.rollback()
            raise
        self._conn.commit()
        return int(cursor.lastrowid or 0)
