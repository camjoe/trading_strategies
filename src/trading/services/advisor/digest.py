"""Build the advisor digest: per book, its strategy's evidence, ledger state, and review flags."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone

from common.time import utc_now_iso
from trading.domain.advisor import build_review_flags, due_for_scoring
from trading.domain.metrics.returns import total_return_pct
from trading.models import AccountRecord
from trading.models.advisor import (
    AdvisorAccountDigest,
    AdvisorBookDigest,
    AdvisorDigest,
    BookEvidence,
    StrategyDecisionRecord,
)
from trading.models.books import BookRecord
from trading.repositories.book_strategy_history import BookStrategyHistoryRepository
from trading.repositories.books import BookRepository
from trading.repositories.snapshots import EquitySnapshotRepository
from trading.repositories.strategies import StrategyRepository
from trading.repositories.strategy_decisions import StrategyDecisionRepository
from trading.services.accounts.mutations import get_account
from trading.services.accounts.queries import list_account_records
from trading.services.evaluation.queries import fetch_strategy_evaluation_for_account_row

# How many of a book's most recent decisions the digest shows.
RECENT_DECISION_LIMIT = 5
# Ledger rows read per account to split into per-book recent lists.
_ACCOUNT_DECISION_SCAN_LIMIT = 200


def build_advisor_digest(
    conn: sqlite3.Connection,
    *,
    account_name: str | None = None,
    as_of: date | None = None,
) -> AdvisorDigest:
    """The digest for one account, or every account when ``account_name`` is None.

    Read-only. Every book is reviewed on its own: its strategy's backtest and walk-forward
    evidence, its paper return since that strategy was assigned, its decisions, and its flags.
    ``as_of`` (default: today, UTC) decides which pending decisions are due for scoring.
    """
    as_of_date = as_of or datetime.now(timezone.utc).date()
    accounts = [get_account(conn, account_name)] if account_name is not None else list_account_records(conn)
    return AdvisorDigest(
        generated_at=utc_now_iso(),
        as_of_date=as_of_date.isoformat(),
        accounts=[_account_digest(conn, account, as_of=as_of_date) for account in accounts],
    )


def _account_digest(conn: sqlite3.Connection, account: AccountRecord, *, as_of: date) -> AdvisorAccountDigest:
    repository = StrategyDecisionRepository(conn)
    recent = repository.fetch_recent(account_id=account.id, limit=_ACCOUNT_DECISION_SCAN_LIMIT)
    due = due_for_scoring(repository.fetch_pending(account_id=account.id), as_of=as_of)
    books = sorted(BookRepository(conn).fetch_for_account(account_id=account.id), key=lambda book: not book.is_default)
    return AdvisorAccountDigest(
        account_name=account.name,
        benchmark_ticker=account.benchmark_ticker,
        books=[_book_digest(conn, account, book, recent=recent, due=due) for book in books],
    )


def _book_digest(
    conn: sqlite3.Connection,
    account: AccountRecord,
    book: BookRecord,
    *,
    recent: list[StrategyDecisionRecord],
    due: list[StrategyDecisionRecord],
) -> AdvisorBookDigest:
    assignment = BookStrategyHistoryRepository(conn).fetch_open(book_id=book.id)
    strategy = (
        StrategyRepository(conn).fetch_by_id(strategy_id=assignment.strategy_id) if assignment is not None else None
    )
    strategy_key = strategy.strategy_key if strategy is not None else None
    assigned_since = assignment.effective_from if assignment is not None else None

    evaluation = fetch_strategy_evaluation_for_account_row(conn, account, strategy_name=strategy_key)
    paper_return, paper_count = _paper_since(conn, book_id=book.id, since=assigned_since)
    evidence = BookEvidence(
        walk_forward=evaluation.walk_forward,
        backtest_freshness=evaluation.diagnostics.backtest_freshness,
        paper_return_pct=paper_return,
        paper_snapshot_count=paper_count,
        data_gaps=list(evaluation.diagnostics.data_gaps),
    )
    book_due = [record for record in due if record.book_id == book.id]
    return AdvisorBookDigest(
        book_name=book.name,
        is_default=bool(book.is_default),
        strategy_key=strategy_key,
        assigned_since=assigned_since,
        evidence=evidence,
        recent_decisions=[record for record in recent if record.book_id == book.id][:RECENT_DECISION_LIMIT],
        due_decisions=book_due,
        flags=build_review_flags(evidence, strategy_key=strategy_key, due_count=len(book_due)),
    )


def _paper_since(conn: sqlite3.Connection, *, book_id: int, since: str | None) -> tuple[float | None, int]:
    """The book's paper return and snapshot count since its strategy was assigned."""
    if since is None:
        return None, 0
    snapshots = EquitySnapshotRepository(conn)
    first = snapshots.fetch_first_for_book_at_or_after(book_id=book_id, iso=since)
    last = snapshots.fetch_latest_for_book(book_id=book_id)
    count = snapshots.fetch_count_for_book_since(book_id=book_id, iso=since)
    if first is None or last is None or first.equity <= 0:
        return None, count
    return total_return_pct(first_equity=float(first.equity), last_equity=float(last.equity)), count
