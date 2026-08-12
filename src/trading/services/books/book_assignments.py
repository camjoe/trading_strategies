"""Book strategy assignments — the single live assignment record.

``book_strategy_history`` is authoritative for which strategy a book runs.
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

from trading.models.books import BookAssignmentView, BookRecord, TradingBook
from trading.repositories.book_strategy_history import BookStrategyHistoryRepository
from trading.repositories.books import BookRepository
from trading.repositories.strategies import StrategyRepository
from trading.services.books.default_book import default_book_id


def _view_from_open_record(conn: sqlite3.Connection, *, book_id: int) -> BookAssignmentView | None:
    record = BookStrategyHistoryRepository(conn).fetch_open(book_id=int(book_id))
    if record is None:
        return None
    strategy = StrategyRepository(conn).fetch_by_id(strategy_id=record.strategy_id)
    if strategy is None:
        raise LookupError(f"Book {book_id} assignment references unknown strategy_id={record.strategy_id}.")
    return BookAssignmentView(
        book_id=int(book_id),
        strategy_id=record.strategy_id,
        strategy_name=strategy.strategy_key,
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


def get_default_book(conn: sqlite3.Connection, *, account_id: int) -> BookRecord | None:
    """The account's default book, or None before bootstrap.

    Service-level accessor for interface layers (which must not import
    repositories directly); execution settings are book columns since
    revision 0004, so this is how displays read an account's effective
    execution configuration.
    """
    return BookRepository(conn).fetch_default_for_account(account_id=int(account_id))


# Shown when an account's default book has no open strategy assignment yet
# (accounts.strategy was dropped in revision 0008 — there is no fallback).
UNASSIGNED_STRATEGY_LABEL = "unassigned"


def active_strategy_for_account(conn: sqlite3.Connection, account_id: int) -> str:
    """The strategy the account's default book actually runs.

    Resolves from the default book's open assignment — the record rotation
    applies to (ADR 014). ``UNASSIGNED_STRATEGY_LABEL`` when no default book
    or open assignment exists yet. Read-only: it never bootstraps the default
    book.
    """
    book = BookRepository(conn).fetch_default_for_account(account_id=int(account_id))
    if book is None:
        return UNASSIGNED_STRATEGY_LABEL
    view = open_assignment_for_book(conn, book_id=book.id)
    if view is not None:
        return view.strategy_name
    return UNASSIGNED_STRATEGY_LABEL


def sync_default_book_assignment(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    strategy_name: str,
    now_iso: str,
) -> BookAssignmentView:
    """Ensure the account's default book openly runs ``strategy_name``.

    Explicit account strategy edits call this so the assignment record —
    which is what actually trades — reflects the requested strategy.
    A no-op when the open assignment already matches, keeping the
    ``effective_from``/``effective_to`` history free of same-strategy churn.
    """
    book_id = default_book_id(conn, account_id=int(account_id))
    current = open_assignment_for_book(conn, book_id=book_id)
    if current is not None and current.strategy_name == strategy_name.strip().lower():
        return current
    return assign_book_strategy(
        conn,
        book_id=book_id,
        strategy_name=strategy_name,
        now_iso=now_iso,
    )


def assign_book_strategy(
    conn: sqlite3.Connection,
    *,
    book_id: int,
    strategy_name: str,
    now_iso: str,
) -> BookAssignmentView:
    """Assign a strategy to the book (closing the open assignment atomically)."""
    strategy_id = StrategyRepository(conn).ensure_id_for_label(label=strategy_name, now_iso=now_iso)
    if strategy_id is None:
        raise ValueError(f"Cannot assign blank strategy label to book {book_id}.")
    BookStrategyHistoryRepository(conn).assign_strategy(
        book_id=int(book_id),
        strategy_id=int(strategy_id),
        effective_from=now_iso,
        created_at=now_iso,
        updated_at=now_iso,
    )
    view = _view_from_open_record(conn, book_id=book_id)
    assert view is not None  # just written above
    return view
