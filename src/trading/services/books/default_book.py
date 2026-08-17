"""Resolve an account to one of its books.

Read-only book resolution for service and interface callers. Raises rather than
creating: ``create_account`` makes the default book, and ``ensure_default_books``
repairs accounts that predate that.
"""

from __future__ import annotations

import sqlite3

from trading.domain.exceptions import NotFoundError
from trading.models.books import BookRecord
from trading.repositories.accounts import AccountRepository
from trading.repositories.books import BookRepository


def default_book_id(conn: sqlite3.Connection, *, account_id: int) -> int:
    book = BookRepository(conn).fetch_default_for_account(account_id=account_id)
    if book is None:
        raise NotFoundError(f"Account {account_id} has no default book.")
    return book.id


def fetch_account_book(
    conn: sqlite3.Connection,
    *,
    account_name: str,
    book_name: str | None = None,
) -> BookRecord:
    """Resolve an account's book by name, or its default book when ``book_name`` is None.

    The single account+book-by-name resolver behind the edit surfaces
    (``configure_book`` and ``parameters.resolve_book_id``). Raises
    ``NotFoundError`` for an unknown account, a missing default book, or a named
    book that does not exist.
    """
    account = AccountRepository(conn).fetch_by_name(account_name=account_name)
    if account is None:
        raise NotFoundError(f"Account not found: {account_name}")
    if book_name is None:
        book = BookRepository(conn).fetch_default_for_account(account_id=account.id)
        if book is None:
            raise NotFoundError(f"Account {account_name} has no default book.")
        return book
    for book in BookRepository(conn).fetch_for_account(account_id=account.id):
        if book.name == book_name:
            return book
    raise NotFoundError(f"Book not found for account {account_name}: {book_name}")
