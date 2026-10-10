from __future__ import annotations

import sqlite3

from trading.models.books import BookRecord
from trading.repositories.accounts import AccountRepository
from trading.repositories.books import BookRepository
from trading.services.accounts.presentation import render_account_listing_lines
from trading.services.books.book_assignments import open_assignment_for_book


def fetch_account_listing_lines(conn: sqlite3.Connection, by_strategy: bool = True) -> list[str]:
    accounts = AccountRepository(conn).fetch_all()
    if not accounts:
        return []
    book_repo = BookRepository(conn)
    default_books: dict[int, BookRecord] = {}
    active_strategies: dict[int, str] = {}
    for account in accounts:
        book = book_repo.fetch_default_for_account(account_id=account.id)
        if book is None:
            continue
        default_books[account.id] = book
        # Derive the active strategy from the already-fetched default book rather
        # than re-fetching it through active_strategy_for_account. A book with no
        # open assignment is left out; the renderer defaults it to unassigned.
        assignment = open_assignment_for_book(conn, book_id=book.id)
        if assignment is not None:
            active_strategies[account.id] = assignment.strategy_name
    return render_account_listing_lines(
        accounts, by_strategy=by_strategy, active_strategies=active_strategies, default_books=default_books
    )
