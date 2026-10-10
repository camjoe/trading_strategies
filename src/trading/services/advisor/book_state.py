"""Read a book's current strategy and its own paper return since that strategy was assigned."""

from __future__ import annotations

import sqlite3

from trading.domain.metrics.returns import total_return_pct
from trading.models.advisor import BookState
from trading.models.books import BookRecord
from trading.repositories.book_strategy_history import BookStrategyHistoryRepository
from trading.repositories.snapshots import EquitySnapshotRepository
from trading.repositories.strategies import StrategyRepository


def fetch_book_state(conn: sqlite3.Connection, book: BookRecord) -> BookState:
    """The book's assigned strategy and paper return, from its own snapshots, not the account roll-up."""
    assignment = BookStrategyHistoryRepository(conn).fetch_open(book_id=book.id)
    strategy = (
        StrategyRepository(conn).fetch_by_id(strategy_id=assignment.strategy_id) if assignment is not None else None
    )
    assigned_since = assignment.effective_from if assignment is not None else None
    paper_return, paper_count = _paper_since(conn, book_id=book.id, since=assigned_since)
    return BookState(
        book_name=book.name,
        is_default=bool(book.is_default),
        strategy_key=strategy.strategy_key if strategy is not None else None,
        assigned_since=assigned_since,
        paper_return_pct=paper_return,
        paper_snapshot_count=paper_count,
    )


def _paper_since(conn: sqlite3.Connection, *, book_id: int, since: str | None) -> tuple[float | None, int]:
    if since is None:
        return None, 0
    snapshots = EquitySnapshotRepository(conn)
    first = snapshots.fetch_first_for_book_at_or_after(book_id=book_id, iso=since)
    last = snapshots.fetch_latest_for_book(book_id=book_id)
    count = snapshots.fetch_count_for_book_since(book_id=book_id, iso=since)
    if first is None or last is None or first.equity <= 0:
        return None, count
    return total_return_pct(first_equity=float(first.equity), last_equity=float(last.equity)), count
