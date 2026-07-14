"""One-time cutover: rotation scheduling moves from accounts onto books (ADR 014).

For every account:

1. Ensure the default book exists (bootstrapped from the account row).
2. Re-sync the retained account rotation columns (``rotation_enabled``,
   ``rotation_schedule``, ``rotation_lookback_days``) onto **every** book of
   the account's — the account columns were the live source of truth until
   the collapse, so earlier seeded copies may be stale, and sleeve-bridged
   books may have no ``book_rotation_settings`` row at all (which would
   silently disable their rotation once the book-owned enabled gate applies).
   Policy columns are preserved.
3. Open the default book's strategy assignment where missing, resolved the
   way the retired account flow did: ``rotation_active_strategy`` if it is in
   the schedule, else ``schedule[rotation_active_index]``, else the base
   ``strategy`` column. Unknown labels get a draft ``strategies`` row so the
   account keeps trading. An existing open assignment is never overwritten —
   books the rotation flow has written to are authoritative.

Idempotent — safe to re-run (step 2 re-copies the same retained values; step 3
skips assigned books). Reads the retained account columns via raw SQL on
purpose; delete this module (and the runbook) once every existing DB has been
migrated.

**Full operator procedure** (backup, run, verify, cleanup):
``docs/runbooks/book-rotation-cutover.md``. Fresh DBs need nothing — accounts
created after the collapse get their book scheduling from profiles/API and
their assignment at creation.

Usage:
    python -m trading.interfaces.runtime.data_ops.migrate_book_rotation
"""

from __future__ import annotations

import sqlite3

from common.time import utc_now_iso
from infrastructure.database.init import db_session
from trading.domain.rotation import parse_rotation_schedule
from trading.repositories.book_bridge import default_book_id, strategy_id_for_label
from trading.repositories.book_settings import BookRotationSettingsRepository
from trading.repositories.books import BookRepository
from trading.services.books.book_assignments import assign_book_strategy, open_assignment_for_book


def _legacy_active_strategy(account: sqlite3.Row) -> str | None:
    """The strategy the retired account rotation flow considered active."""
    try:
        schedule = [name for name in parse_rotation_schedule(account["rotation_schedule"]) if name]
    except ValueError:
        schedule = []
    active = str(account["rotation_active_strategy"] or "").strip()
    if not schedule:
        base = str(account["strategy"] or "").strip()
        return active or base or None
    if active and active in schedule:
        return active
    index = int(account["rotation_active_index"] or 0)
    return schedule[index % len(schedule)]


def migrate_book_rotation(conn: sqlite3.Connection) -> tuple[int, int]:
    """Sync book rotation scheduling + default-book assignments.

    Returns ``(scheduling_rows_synced, assignments_opened)``.
    """
    now_iso = utc_now_iso()
    book_repo = BookRepository(conn)
    settings_repo = BookRotationSettingsRepository(conn)
    scheduling_synced = 0
    assignments_opened = 0

    accounts = conn.execute(
        "SELECT id, strategy, rotation_enabled, rotation_schedule, rotation_lookback_days,"
        " rotation_active_index, rotation_active_strategy FROM accounts ORDER BY id ASC"
    ).fetchall()
    for account in accounts:
        account_id = int(account["id"])
        book_id = default_book_id(conn, account_id)

        lookback = account["rotation_lookback_days"]
        for book in book_repo.fetch_for_account(account_id=account_id):
            current = settings_repo.fetch(book_id=book.id)
            settings_repo.upsert_rotation_scheduling(
                book_id=book.id,
                rotation_enabled=int(account["rotation_enabled"] or 0),
                rotation_lookback_days=int(lookback) if lookback else None,
                rotation_schedule=account["rotation_schedule"],
                created_at=current.created_at if current is not None else now_iso,
                updated_at=now_iso,
            )
            scheduling_synced += 1

        if open_assignment_for_book(conn, book_id=book_id) is None:
            strategy_name = _legacy_active_strategy(account)
            if strategy_name and strategy_id_for_label(conn, strategy_name, now_iso=now_iso) is not None:
                assign_book_strategy(
                    conn,
                    book_id=book_id,
                    strategy_name=strategy_name,
                    now_iso=now_iso,
                )
                assignments_opened += 1

    conn.commit()
    return scheduling_synced, assignments_opened


def main() -> int:
    with db_session() as conn:
        scheduling_synced, assignments_opened = migrate_book_rotation(conn)
    print(f"book rotation cutover: scheduling rows synced={scheduling_synced} assignments opened={assignments_opened}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
