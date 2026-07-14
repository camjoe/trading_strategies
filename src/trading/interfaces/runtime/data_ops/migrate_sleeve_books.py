"""One-time migration: mirror legacy sleeves onto their books (sleeve retirement).

Replaces the retired runtime lazy sweep. For every legacy ``strategy_sleeves`` row:
ensure the bridging book exists (same account + name), mirror the sleeve's status and
trade universes, and copy its open strategy assignment onto the book when the book has
none. Idempotent — safe to re-run; existing book state is never overwritten by a
second run (books are authoritative once populated).

**Full operator procedure** (backup, run, verify, table drops, tooling cleanup):
``docs/runbooks/sleeve-retirement-db-migration.md``. Fresh DBs no longer create
the legacy tables; this op detects that and exits as a no-op.

Reads the legacy tables via raw SQL on purpose; delete this module (and the
runbook) once every existing DB has been migrated and dropped.

Usage:
    python -m trading.interfaces.runtime.data_ops.migrate_sleeve_books
"""

from __future__ import annotations

import sqlite3

from common.time import utc_now_iso
from infrastructure.database.init import db_session
from trading.repositories.book_assignments import BookAssignmentRepository
from trading.repositories.book_bridge import strategy_id_for_label
from trading.repositories.books import BookRepository

# Legacy sleeve status → clean book status (books use 'closed' where sleeves used 'retired').
_SLEEVE_TO_BOOK_STATUS = {"active": "active", "paused": "paused", "retired": "closed"}


def migrate_sleeve_books(conn: sqlite3.Connection) -> tuple[int, int]:
    """Mirror every legacy sleeve onto its book; returns (books_created, assignments_copied)."""
    now_iso = utc_now_iso()
    book_repo = BookRepository(conn)
    assignment_repo = BookAssignmentRepository(conn)
    books_created = 0
    assignments_copied = 0

    try:
        sleeves = conn.execute(
            "SELECT id, account_id, name, status, start_equity, current_cash, current_equity,"
            " trade_universes, created_at FROM strategy_sleeves ORDER BY id ASC"
        ).fetchall()
    except sqlite3.OperationalError:
        # Fresh DB: the legacy tables never existed — nothing to migrate.
        return 0, 0
    for sleeve in sleeves:
        row = conn.execute(
            "SELECT id FROM books WHERE account_id = ? AND name = ?",
            (int(sleeve["account_id"]), str(sleeve["name"])),
        ).fetchone()
        if row is not None:
            book_id = int(row[0])
        else:
            book_id = book_repo.insert(
                account_id=int(sleeve["account_id"]),
                name=str(sleeve["name"]),
                is_default=0,
                start_equity=float(sleeve["start_equity"]),
                current_cash=float(sleeve["current_cash"]),
                current_equity=float(sleeve["current_equity"]),
                created_at=str(sleeve["created_at"]),
                updated_at=str(sleeve["created_at"]),
            )
            books_created += 1

        book = book_repo.fetch_by_id(book_id=book_id)
        assert book is not None
        target_status = _SLEEVE_TO_BOOK_STATUS.get(str(sleeve["status"]).strip().lower(), "active")
        if book.status != target_status:
            book_repo.update_status(book_id=book_id, status=target_status, updated_at=now_iso)
        if book.trade_universes != sleeve["trade_universes"]:
            book_repo.update_trade_universes(
                book_id=book_id, trade_universes=sleeve["trade_universes"], updated_at=now_iso
            )

        if assignment_repo.fetch_open(book_id=book_id) is not None:
            continue
        legacy = conn.execute(
            "SELECT strategy_name, effective_from, created_at, updated_at"
            " FROM sleeve_strategy_assignments"
            " WHERE sleeve_id = ? AND effective_to IS NULL"
            " ORDER BY id DESC LIMIT 1",
            (int(sleeve["id"]),),
        ).fetchone()
        if legacy is None:
            continue
        strategy_id = strategy_id_for_label(conn, str(legacy["strategy_name"]), now_iso=str(legacy["created_at"]))
        if strategy_id is None:
            continue
        assignment_repo.assign_strategy(
            book_id=book_id,
            strategy_id=int(strategy_id),
            effective_from=str(legacy["effective_from"]),
            created_at=str(legacy["created_at"]),
            updated_at=str(legacy["updated_at"]),
        )
        assignments_copied += 1

    return books_created, assignments_copied


def main() -> None:
    with db_session() as conn:
        books_created, assignments_copied = migrate_sleeve_books(conn)
        print(f"bridging books created: {books_created}")
        print(f"assignments copied: {assignments_copied}")


if __name__ == "__main__":
    main()
