"""Read orchestration for the book rotation settings change-audit trail."""

from __future__ import annotations

import sqlite3

from trading.models.books import BookRotationSettingsChangeEvent
from trading.repositories.book_rotation_settings import BookRotationSettingsRepository
from trading.services.parameters.mutations import resolve_book_id


def fetch_book_rotation_change_history(
    conn: sqlite3.Connection,
    *,
    account_name: str,
    book_name: str | None = None,
    limit: int = 20,
) -> list[BookRotationSettingsChangeEvent]:
    book_id = resolve_book_id(conn, account_name=account_name, book_name=book_name)
    return BookRotationSettingsRepository(conn).fetch_change_events(book_id=book_id, limit=limit)


__all__ = ["fetch_book_rotation_change_history"]
