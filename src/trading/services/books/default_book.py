"""Resolve an account to its default book.

The successor to the retired ``repositories/book_bridge.py``. That module
bootstrapped a missing book; this one raises, because every account created
since gets its book in ``create_account``. Run ``ensure_default_books`` to
repair accounts that predate it.
"""

from __future__ import annotations

import sqlite3

from trading.domain.exceptions import NotFoundError
from trading.repositories.books import BookRepository


def default_book_id(conn: sqlite3.Connection, *, account_id: int) -> int:
    book = BookRepository(conn).fetch_default_for_account(account_id=account_id)
    if book is None:
        raise NotFoundError(f"Account {account_id} has no default book.")
    return book.id
