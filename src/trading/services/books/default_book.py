"""Resolve an account to its default book.

Raises rather than creating one: ``create_account`` makes the book, and
``ensure_default_books`` repairs accounts that predate that.
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
