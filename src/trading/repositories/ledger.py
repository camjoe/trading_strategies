from __future__ import annotations

import sqlite3

from trading.models.books.ledger_entry_record import LedgerEntryRecord
from trading.repositories.unit_of_work import commit_unit_of_work


class LedgerRepository:
    """SQL access for the clean-schema book-keyed ledger."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def _row_to_record(self, row: sqlite3.Row) -> LedgerEntryRecord:
        return LedgerEntryRecord.from_mapping(dict(row))

    def insert(
        self,
        *,
        book_id: int,
        entry_type: str,
        amount: float,
        reference_type: str | None = None,
        reference_id: str | None = None,
        entry_time: str,
        created_at: str,
    ) -> int:
        cursor = self._conn.execute(
            """
            INSERT INTO ledger (
                book_id, entry_type, amount, reference_type, reference_id,
                entry_time, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(book_id),
                entry_type,
                float(amount),
                reference_type,
                reference_id,
                entry_time,
                created_at,
            ),
        )
        commit_unit_of_work(self._conn)
        return int(cursor.lastrowid or 0)

    def fetch_for_book(self, *, book_id: int) -> list[LedgerEntryRecord]:
        rows = self._conn.execute(
            "SELECT * FROM ledger WHERE book_id = ? ORDER BY entry_time ASC, id ASC",
            (int(book_id),),
        ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def fetch_cash_events_for_account(self, *, account_id: int) -> list[LedgerEntryRecord]:
        """Deposit/withdrawal entries across all of the account's books, oldest first."""
        rows = self._conn.execute(
            """
            SELECT l.*
            FROM ledger l
            JOIN books b ON b.id = l.book_id
            WHERE b.account_id = ? AND l.entry_type IN ('deposit', 'withdrawal')
            ORDER BY l.entry_time ASC, l.id ASC
            """,
            (int(account_id),),
        ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def fetch_by_reference(self, *, reference_type: str, reference_id: str) -> list[LedgerEntryRecord]:
        rows = self._conn.execute(
            "SELECT * FROM ledger WHERE reference_type = ? AND reference_id = ? ORDER BY id ASC",
            (reference_type, reference_id),
        ).fetchall()
        return [self._row_to_record(row) for row in rows]
