"""Book strategy assignments — the single live assignment record (sleeve retirement SR-1).

``book_strategy_assignments`` is authoritative for which strategy a book runs.
This module owns the two trading-path seams:

- ``open_assignment_for_book`` — read a book's open assignment. During the
  retirement window it lazily bootstraps from the book's legacy sleeve
  assignment (mirroring ``book_bridge``'s lazy-create pattern), so existing DBs
  migrate themselves on first read.
- ``assign_book_strategy`` — write a new assignment (rotation's apply step).
  Until every sleeve-assignment reader is migrated (SR-3/SR-4), the legacy
  sleeve row is kept in sync as a secondary write; that dual-write dies in SR-6.
"""

from __future__ import annotations

import sqlite3

from trading.models.books.book_assignment_view import BookAssignmentView
from trading.repositories.book_assignments import BookAssignmentRepository
from trading.repositories.book_bridge import strategy_id_for_label
from trading.repositories.sleeves import SleeveRepository
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


def open_assignment_for_book(
    conn: sqlite3.Connection,
    *,
    book_id: int,
    legacy_sleeve_id: int | None = None,
) -> BookAssignmentView | None:
    """The book's open assignment, or None when the book runs no strategy.

    When the book has no open assignment but its legacy sleeve does
    (``legacy_sleeve_id`` given), the sleeve assignment is copied to the book
    once — the idempotent bootstrap that migrates existing DBs at first read.
    """
    view = _view_from_open_record(conn, book_id=book_id)
    if view is not None or legacy_sleeve_id is None:
        return view

    legacy = SleeveRepository(conn).fetch_active_assignment(sleeve_id=int(legacy_sleeve_id))
    if legacy is None:
        return None
    strategy_id = strategy_id_for_label(conn, legacy.strategy_name, now_iso=legacy.created_at)
    if strategy_id is None:
        return None
    BookAssignmentRepository(conn).assign_strategy(
        book_id=int(book_id),
        strategy_id=int(strategy_id),
        param_set_id=legacy.param_set_id,
        effective_from=legacy.effective_from,
        created_at=legacy.created_at,
        updated_at=legacy.updated_at,
    )
    return _view_from_open_record(conn, book_id=book_id)


def assign_book_strategy(
    conn: sqlite3.Connection,
    *,
    book_id: int,
    strategy_name: str,
    param_set_id: int | None,
    now_iso: str,
    legacy_sleeve_id: int | None = None,
) -> BookAssignmentView:
    """Assign a strategy to the book (closing the open assignment atomically).

    The book write is authoritative. When ``legacy_sleeve_id`` is given, the
    legacy sleeve assignment is kept in sync so not-yet-migrated readers
    (reporting/governance) stay correct until SR-3/SR-4 land.
    """
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

    if legacy_sleeve_id is not None:
        sleeve_repo = SleeveRepository(conn)
        sleeve_repo.close_active_assignment(
            sleeve_id=int(legacy_sleeve_id),
            effective_to=now_iso,
            updated_at=now_iso,
        )
        sleeve_repo.insert_assignment(
            sleeve_id=int(legacy_sleeve_id),
            strategy_name=strategy_name,
            param_set_id=param_set_id,
            effective_from=now_iso,
            effective_to=None,
            is_incumbent=1,
            created_at=now_iso,
            updated_at=now_iso,
        )

    view = _view_from_open_record(conn, book_id=book_id)
    assert view is not None  # just written above
    return view
