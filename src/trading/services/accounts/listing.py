from __future__ import annotations

import sqlite3

from trading.models.books import BookRecord
from trading.repositories.accounts import AccountRepository
from trading.repositories.books import BookRepository
from trading.services.accounts.presentation import build_account_listing_lines
from trading.services.books.book_assignments import active_strategy_for_account


def list_accounts(conn: sqlite3.Connection, by_strategy: bool = True) -> list[str]:
    accounts = AccountRepository(conn).fetch_all()
    if not accounts:
        return []
    active_strategies = {account.id: active_strategy_for_account(conn, account.id) for account in accounts}
    book_repo = BookRepository(conn)
    default_books: dict[int, BookRecord] = {}
    for account in accounts:
        book = book_repo.fetch_default_for_account(account_id=account.id)
        if book is not None:
            default_books[account.id] = book
    return build_account_listing_lines(
        accounts, by_strategy=by_strategy, active_strategies=active_strategies, default_books=default_books
    )
