from __future__ import annotations

import sqlite3
from collections.abc import Mapping

from trading.models.books import BookRecord
from trading.persistence.unit_of_work import commit_unit_of_work


class BookRepository:
    """SQL access for books — the clean-schema execution primitive.

    The one-default-book-per-account invariant is enforced by the partial unique
    index `idx_books_default_per_account`; violations surface as
    sqlite3.IntegrityError.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(
        self,
        *,
        account_id: int,
        name: str,
        status: str = "active",
        is_default: int = 0,
        start_equity: float,
        current_cash: float,
        current_equity: float,
        # Explicitly unset. Resolving a universe name to symbols is service
        # work (revision 0029), so the repository has no default to offer.
        trade_symbols: str = "[]",
        created_at: str,
        updated_at: str,
    ) -> int:
        """Create a book with its identity, opening balances, and universe.

        Execution, risk, goal, and option settings are not arguments here. They
        are columns on `books` (revisions 0004/0005) that every one of them
        either defaults or nulls at creation, and callers apply them afterwards
        through `update`. The two other insert paths — `book_bridge`'s
        default-book bootstrap and the fixture seeder — write these same columns.
        """
        cursor = self._conn.execute(
            """
            INSERT INTO books (
                account_id, name, status, is_default, start_equity, current_cash,
                current_equity, trade_symbols, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                account_id,
                name,
                status,
                is_default,
                start_equity,
                current_cash,
                current_equity,
                trade_symbols,
                created_at,
                updated_at,
            ),
        )
        book_id = int(cursor.lastrowid or 0)
        self._record_universe_history(book_id=book_id, trade_symbols=trade_symbols, effective_from=created_at)
        commit_unit_of_work(self._conn)
        return book_id

    def _record_universe_history(self, *, book_id: int, trade_symbols: str, effective_from: str) -> None:
        """Close the open universe-history row (if any) and open a new one.

        `book_universe_history` records the **resolved ticker set** effective over
        each interval, not the universe names (revision 0029) — so what a book was
        actually trading on a past date stays reconstructable even after a universe
        file is edited. That is the point-in-time guarantee backtest and evaluation
        integrity rest on.

        Nothing reads the table yet; the read side has not been built. The writes
        still matter: history only exists later if it is recorded now, so do not
        take the absent reader as a sign these are dead.
        """
        self._conn.execute(
            "UPDATE book_universe_history SET effective_to = ? WHERE book_id = ? AND effective_to IS NULL",
            (effective_from, book_id),
        )
        self._conn.execute(
            """
            INSERT INTO book_universe_history (book_id, trade_symbols, effective_from, effective_to)
            VALUES (?, ?, ?, NULL)
            """,
            (book_id, trade_symbols, effective_from),
        )

    def update(self, *, book_id: int, values: Mapping[str, object], updated_at: str) -> None:
        """Write ``values`` as a partial column update to one book; no-op when empty.

        Callers pass column name to value; deciding which columns to include
        (and so which to leave at their current value) is theirs.
        """
        if not values:
            return
        assignments = ", ".join(f"{column} = ?" for column in values)
        self._conn.execute(
            f"UPDATE books SET {assignments}, updated_at = ? WHERE id = ?",
            (*values.values(), updated_at, book_id),
        )
        commit_unit_of_work(self._conn)

    def fetch_by_id(self, *, book_id: int) -> BookRecord | None:
        row = self._conn.execute(
            "SELECT * FROM books WHERE id = ?",
            (book_id,),
        ).fetchone()
        return BookRecord.from_mapping(dict(row)) if row is not None else None

    def fetch_for_account(self, *, account_id: int) -> list[BookRecord]:
        rows = self._conn.execute(
            "SELECT * FROM books WHERE account_id = ? ORDER BY id ASC",
            (account_id,),
        ).fetchall()
        return [BookRecord.from_mapping(dict(row)) for row in rows]

    def fetch_default_for_account(self, *, account_id: int) -> BookRecord | None:
        row = self._conn.execute(
            "SELECT * FROM books WHERE account_id = ? AND is_default = 1",
            (account_id,),
        ).fetchone()
        return BookRecord.from_mapping(dict(row)) if row is not None else None

    def update_status(self, *, book_id: int, status: str, updated_at: str) -> None:
        self.update(book_id=book_id, values={"status": status}, updated_at=updated_at)

    def update_trade_symbols(self, *, book_id: int, trade_symbols: str, updated_at: str) -> None:
        """Set the book's universes and record the change in the history table."""
        self._conn.execute(
            "UPDATE books SET trade_symbols = ?, updated_at = ? WHERE id = ?",
            (trade_symbols, updated_at, book_id),
        )
        self._record_universe_history(book_id=book_id, trade_symbols=trade_symbols, effective_from=updated_at)
        commit_unit_of_work(self._conn)

    def update_balances(
        self,
        *,
        book_id: int,
        current_cash: float,
        current_equity: float,
        updated_at: str,
    ) -> None:
        self.update(
            book_id=book_id,
            values={"current_cash": current_cash, "current_equity": current_equity},
            updated_at=updated_at,
        )
