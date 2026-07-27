"""Read orchestration for the book rotation settings change-audit trail."""

from __future__ import annotations

import sqlite3

from trading.models.books.book_rotation_settings_change_event import BookRotationSettingsChangeEvent
from trading.repositories.book_settings import BookRotationSettingsRepository
from trading.services.parameters.mutations import _resolve_book_id


def fetch_book_rotation_change_history(
    conn: sqlite3.Connection,
    *,
    account_name: str,
    book_name: str | None = None,
    limit: int = 20,
) -> list[BookRotationSettingsChangeEvent]:
    book_id = _resolve_book_id(conn, account_name=account_name, book_name=book_name)
    return BookRotationSettingsRepository(conn).fetch_change_events(book_id=book_id, limit=limit)


__all__ = ["fetch_book_rotation_change_history"]
