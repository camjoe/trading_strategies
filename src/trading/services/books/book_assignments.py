"""Book strategy assignments — the single live assignment record.

``book_strategy_assignments`` is authoritative for which strategy a book runs.
This module owns the assignment seams and the two book enumerations:

- ``open_assignment_for_book`` / ``assign_book_strategy`` — read/write a book's
  open assignment (rotation's apply step writes here).
- ``sync_default_book_assignment`` — keep the default book's assignment in step
  with explicit account strategy edits.
- ``enumerate_trading_books`` — the books eligible to trade (active, openly
  assigned; the default book included).
- ``list_report_books`` — the read-side enumeration for reporting/monitoring/
  governance (non-default books of any status, with their open assignments).
"""

from __future__ import annotations

import sqlite3

from trading.models.books.book_assignment_view import BookAssignmentView
from trading.models.books.book_record import BookRecord
from trading.models.books.trading_book import TradingBook
from trading.repositories.book_assignments import BookAssignmentRepository
from trading.repositories.book_bridge import default_book_id, strategy_id_for_label
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
    """The account's books eligible to trade: active and openly assigned.

    The book-native enumeration both trading and shadow evaluation iterate.
    The default book trades like any other book (the execution-mode collapse,
    ADR 010/014). Unassigned or non-active books do not trade — no account
    fallback.
    """
    trading_books: list[TradingBook] = []
    for book in BookRepository(conn).fetch_for_account(account_id=int(account_id)):
        if book.status.strip().lower() != "active":
            continue
        assignment = open_assignment_for_book(conn, book_id=book.id)
        if assignment is None:
            continue
        trading_books.append(TradingBook(book=book, assignment=assignment))
    return trading_books


def active_strategy_for_account(conn: sqlite3.Connection, account_id: int, *, fallback: str) -> str:
    """The strategy the account's default book actually runs.

    Resolves from the default book's open assignment — the record rotation
    applies to (ADR 014) — falling back to the account's base ``strategy``
    column when no default book or assignment exists yet. Read-only: it never
    bootstraps the default book.
    """
    book = BookRepository(conn).fetch_default_for_account(account_id=int(account_id))
    if book is None:
        return fallback.strip()
    view = open_assignment_for_book(conn, book_id=book.id)
    if view is not None:
        return view.strategy_name
    return fallback.strip()


def sync_default_book_assignment(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    strategy_name: str,
    now_iso: str,
) -> BookAssignmentView:
    """Ensure the account's default book openly runs ``strategy_name``.

    Explicit account strategy edits call this so the assignment record —
    which is what actually trades — follows the account's strategy column.
    A no-op when the open assignment already matches, keeping the
    ``effective_from``/``effective_to`` history free of same-strategy churn.
    """
    book_id = default_book_id(conn, int(account_id))
    current = open_assignment_for_book(conn, book_id=book_id)
    if current is not None and current.strategy_name == strategy_name.strip().lower():
        return current
    return assign_book_strategy(
        conn,
        book_id=book_id,
        strategy_name=strategy_name,
        param_set_id=None,
        now_iso=now_iso,
    )


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
