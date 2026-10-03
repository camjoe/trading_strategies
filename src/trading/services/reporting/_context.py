"""Shared read helper for the printed report renderers.

``account`` and ``comparison`` both resolve the same prelude — the account's
active strategy and default book — before rendering their policy/goal lines.
This owns that shared read so the two reports cannot drift. Unlike
``_formatting`` (I/O-free string helpers), this reaches the database.
"""

from __future__ import annotations

import sqlite3

from trading.models import AccountRecord
from trading.models.books import BookRecord
from trading.repositories.books import BookRepository
from trading.services.books.book_assignments import active_strategy_for_account


def resolve_render_context(conn: sqlite3.Connection, account: AccountRecord) -> tuple[str, BookRecord | None]:
    """The account's active strategy and default book for the report header."""
    account_id = account.id
    active_strategy = active_strategy_for_account(conn, account_id=account_id)
    return active_strategy, BookRepository(conn).fetch_default_for_account(account_id=account_id)


__all__ = ["resolve_render_context"]
