"""Book strategy assignments — the single live assignment record.

``book_strategy_assignments`` is authoritative for which strategy a book runs.
This module owns the assignment seams and the two book enumerations:

- ``open_assignment_for_book`` / ``assign_book_strategy`` — read/write a book's
  open assignment (rotation's apply step writes here).
- ``enumerate_trading_books`` — the books eligible to trade (active,
  non-default, openly assigned).
- ``list_report_books`` — the read-side enumeration for reporting/monitoring/
  governance (non-default books of any status, with their open assignments).
"""

from __future__ import annotations

import sqlite3

from trading.models.books.book_assignment_view import BookAssignmentView
from trading.models.books.book_record import BookRecord
from trading.models.books.trading_book import TradingBook
from trading.repositories.book_assignments import BookAssignmentRepository
from trading.repositories.book_bridge import strategy_id_for_label
from trading.repositories.books import BookRepository
from trading.repositories.strategies import StrategyRepository


def _view_from_open_record(conn: sqlite3.Connection, *, book_id: int) -> BookAssignmentView | None:
    record = BookAssignmentRepository(conn).fetch_open(book_id=int(book_id))
    if record is None:
        return None
    strategy = StrategyRepository(conn).fetch_by_id(strategy_id=record.strategy_id)
    if strategy is None:
        raise LookupError(f"Book {book_id} assignment references unknown strategy_id={record.strategy_id}.")
    return BookAssignmentView(
        book_id=int(book_id),
        strategy_id=record.strategy_id,
        strategy_name=strategy.strategy_key,
        param_set_id=record.param_set_id,
    )


def open_assignment_for_book(conn: sqlite3.Connection, *, book_id: int) -> BookAssignmentView | None:
    """The book's open assignment, or None when the book runs no strategy."""
    return _view_from_open_record(conn, book_id=book_id)


def list_report_books(
    conn: sqlite3.Connection, *, account_id: int
) -> list[tuple[BookRecord, BookAssignmentView | None]]:
    """The account's non-default books (any status) with their open assignments.

    The read-side enumeration for reporting/monitoring/governance surfaces —
    unlike ``enumerate_trading_books`` it includes paused/closed and unassigned
    books, since reports show them.
    """
    return [
        (book, open_assignment_for_book(conn, book_id=book.id))
        for book in BookRepository(conn).fetch_for_account(account_id=int(account_id))
        if not book.is_default
    ]


def enumerate_trading_books(conn: sqlite3.Connection, *, account_id: int) -> list[TradingBook]:
    """The account's books eligible to trade: active, non-default, openly assigned.

    The book-native enumeration both multi-book trading and shadow evaluation
    iterate. Unassigned or non-active books do not trade — no account fallback.
    """
    trading_books: list[TradingBook] = []
    for book in BookRepository(conn).fetch_for_account(account_id=int(account_id)):
        if book.is_default or book.status.strip().lower() != "active":
            continue
        assignment = open_assignment_for_book(conn, book_id=book.id)
        if assignment is None:
            continue
        trading_books.append(TradingBook(book=book, assignment=assignment))
    return trading_books


def assign_book_strategy(
    conn: sqlite3.Connection,
    *,
    book_id: int,
    strategy_name: str,
    param_set_id: int | None,
    now_iso: str,
) -> BookAssignmentView:
    """Assign a strategy to the book (closing the open assignment atomically)."""
    strategy_id = strategy_id_for_label(conn, strategy_name, now_iso=now_iso)
    if strategy_id is None:
        raise ValueError(f"Cannot assign blank strategy label to book {book_id}.")
    BookAssignmentRepository(conn).assign_strategy(
        book_id=int(book_id),
        strategy_id=int(strategy_id),
        param_set_id=param_set_id,
        effective_from=now_iso,
        created_at=now_iso,
        updated_at=now_iso,
    )
    view = _view_from_open_record(conn, book_id=book_id)
    assert view is not None  # just written above
    return view
