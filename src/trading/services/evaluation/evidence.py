from __future__ import annotations

import sqlite3
from dataclasses import replace

from common.coercion import row_expect_int, row_expect_str, row_int, row_str
from trading.domain.evaluation.backtest_freshness import assess_backtest_freshness
from trading.domain.evaluation.confidence import (
    EvaluationConfidenceSettings,
    compute_backtest_confidence,
    compute_blended_score,
    compute_overall_confidence,
    compute_paper_live_confidence,
)
from trading.domain.metrics.returns import safe_return_pct
from trading.models import AccountRecord, EquitySnapshotRecord
from trading.models.evaluation import (
    EvaluationBacktestEvidence,
    EvaluationBasicScope,
    EvaluationConfidence,
    EvaluationDiagnostics,
    EvaluationPaperLiveEvidence,
    EvaluationWalkForwardEvidence,
)
from trading.repositories.rotation_decisions import RotationDecisionRepository
from trading.repositories.snapshots import EquitySnapshotRepository
from trading.services.books.book_assignments import active_strategy_for_account, get_default_book
from trading.services.books.default_book import default_book_id
from trading.services.books.rotation.engine import resolve_default_book_rotation_schedule

# Current non-broker-managed evaluation evidence mode for standard accounts.
PAPER_EVIDENCE_MODE = "paper"

# Evaluation mode label for accounts explicitly enabled for live broker trading.
LIVE_EVIDENCE_MODE = "live"

# Account-wide snapshot evidence is only strategy-safe for non-rotating accounts.
ACCOUNT_SNAPSHOT_SOURCE_LEVEL = "account_snapshot"

# A book snapshot window for the currently-active strategy gives strategy-isolated
# in-flight evidence (the book has run only this strategy since it went active).
ACTIVE_STRATEGY_WINDOW_SOURCE_LEVEL = "book_active_strategy"

# A closed book snapshot window gives strategy-isolated historical evidence for a
# strategy the book has since rotated away from.
CLOSED_STRATEGY_WINDOW_SOURCE_LEVEL = "book_closed_strategy"

# Diagnostics key used when no strategy-matched backtest rows are persisted.
BACKTEST_EVIDENCE_GAP = "missing_backtest_evidence"

# Diagnostics key used when no strategy-safe paper/live rows are persisted.
PAPER_LIVE_EVIDENCE_GAP = "missing_paper_live_evidence"

# Diagnostics key used when no walk-forward window evidence is persisted.
WALK_FORWARD_EVIDENCE_GAP = "missing_walk_forward_evidence"


def _active_strategy(conn: sqlite3.Connection, account: AccountRecord) -> str:
    return active_strategy_for_account(conn, row_expect_int(account, "id"))


def _default_book_rotation_enabled(conn: sqlite3.Connection, account_id: int) -> bool:
    """Whether the account's default book rotates (book-owned, ADR 014).

    The evidence windows are sliced by the default book's rotation-decision
    timeline, so the isolation question is exactly whether that book's
    strategy churns. Read-only: a missing default book means no rotation.
    """
    return resolve_default_book_rotation_schedule(conn, account_id=account_id).rotation_enabled


def resolve_requested_strategy(conn: sqlite3.Connection, account: AccountRecord, strategy_name: str | None) -> str:
    if strategy_name is not None:
        normalized = strategy_name.strip()
        if normalized:
            return normalized
    return _active_strategy(conn, account)


def build_basic_scope(
    conn: sqlite3.Connection, account: AccountRecord, requested_strategy: str
) -> EvaluationBasicScope:
    account_id = row_expect_int(account, "id")
    # instrument_mode is a book column (revision 0004): the default book
    # carries the mode the evaluated account trades under.
    default_book = get_default_book(conn, account_id=account_id)
    return EvaluationBasicScope(
        account_id=account_id,
        account_name=row_expect_str(account, "name"),
        descriptive_name=row_str(account, "descriptive_name"),
        requested_strategy=requested_strategy,
        # accounts.strategy was dropped (revision 0008): the assignment-derived
        # active strategy is the only strategy.
        active_strategy=_active_strategy(conn, account),
        benchmark_ticker=row_expect_str(account, "benchmark_ticker"),
        instrument_mode=default_book.instrument_mode if default_book is not None else None,
        rotation_enabled=_default_book_rotation_enabled(conn, account_id),
        live_trading_enabled=bool(row_int(account, "live_trading_enabled")),
    )


def _evidence_mode(account: AccountRecord) -> str:
    return LIVE_EVIDENCE_MODE if bool(row_int(account, "live_trading_enabled")) else PAPER_EVIDENCE_MODE


def _resolve_strategy_window(
    timeline: list[tuple[str, str]],
    *,
    requested_strategy: str,
) -> tuple[str, str | None] | None:
    """Return ``(window_start, window_end)`` for the requested strategy's most recent run.

    ``timeline`` is the book's active-strategy boundaries as ``(start_time, strategy)``
    ordered oldest-first, each segment active until the next one starts (the last is
    active up to now). Returns ``None`` when the strategy never held the book;
    ``window_end`` is ``None`` when the requested strategy is the one currently active.
    """
    latest_index: int | None = None
    for index, (_start, strategy) in enumerate(timeline):
        if strategy == requested_strategy:
            latest_index = index
    if latest_index is None:
        return None

    run_start = latest_index
    while run_start - 1 >= 0 and timeline[run_start - 1][1] == requested_strategy:
        run_start -= 1

    window_start = timeline[run_start][0]
    is_currently_active = latest_index == len(timeline) - 1
    window_end = None if is_currently_active else timeline[latest_index + 1][0]
    return window_start, window_end


def _book_strategy_window_timeline(
    conn: sqlite3.Connection,
    *,
    account: AccountRecord,
    book_id: int,
    inception_time: str,
) -> list[tuple[str, str]]:
    """Build the book's active-strategy timeline from its rotation-decision log.

    Before the first decision the book ran the first decision's incumbent (or, with
    no decisions, the account's active strategy) since inception; each decision then
    starts a segment for its selected strategy.
    """
    decisions = RotationDecisionRepository(conn).fetch_selected_strategy_timeline(book_id=book_id)
    if not decisions:
        base_strategy = _active_strategy(conn, account)
        return [(inception_time, base_strategy)] if base_strategy else []

    inception_strategy = decisions[0][1] or _active_strategy(conn, account)
    timeline: list[tuple[str, str]] = []
    if inception_strategy:
        timeline.append((inception_time, inception_strategy))
    for decision_time, _incumbent, selected in decisions:
        if selected:
            timeline.append((decision_time, selected))
    return timeline


def _book_strategy_evidence(
    conn: sqlite3.Connection,
    *,
    account: AccountRecord,
    account_id: int,
    requested_strategy: str,
    latest_snapshot: EquitySnapshotRecord | None,
) -> EvaluationPaperLiveEvidence:
    """Strategy-isolated paper-live evidence sliced from book snapshots + rotation decisions.

    Replaces the retired ``rotation_episodes`` store: the account's default-book
    equity snapshots are windowed at the strategy boundaries recorded in
    ``rotation_decisions``, reproducing the per-strategy live returns episodes gave.
    """
    snapshots = EquitySnapshotRepository(conn)
    earliest_snapshot = snapshots.fetch_earliest(account_id=account_id)
    if earliest_snapshot is None or latest_snapshot is None:
        return EvaluationPaperLiveEvidence()

    book_id = default_book_id(conn, account_id=account_id)
    timeline = _book_strategy_window_timeline(
        conn,
        account=account,
        book_id=book_id,
        inception_time=earliest_snapshot.snapshot_time,
    )
    window = _resolve_strategy_window(timeline, requested_strategy=requested_strategy)
    if window is None:
        return EvaluationPaperLiveEvidence()

    window_start, window_end = window
    starting_snapshot = snapshots.fetch_first_at_or_after(account_id=account_id, iso=window_start)
    if starting_snapshot is None:
        return EvaluationPaperLiveEvidence()
    starting_equity = starting_snapshot.equity

    # Declared up front: the open-window branch assigns a known-present snapshot,
    # the closed-window branch a lookup that may miss and returns early.
    ending_snapshot: EquitySnapshotRecord | None
    if window_end is None:
        ending_snapshot = latest_snapshot
        source_level = ACTIVE_STRATEGY_WINDOW_SOURCE_LEVEL
        end_time = latest_snapshot.snapshot_time
    else:
        ending_snapshot = snapshots.fetch_last_at_or_before(account_id=account_id, iso=window_end)
        if ending_snapshot is None:
            return EvaluationPaperLiveEvidence()
        source_level = CLOSED_STRATEGY_WINDOW_SOURCE_LEVEL
        end_time = ending_snapshot.snapshot_time

    return EvaluationPaperLiveEvidence(
        available=True,
        source_level=source_level,
        strategy_isolated=True,
        latest_snapshot_time=end_time,
        snapshot_count=snapshots.fetch_count_between(account_id=account_id, start_iso=window_start, end_iso=end_time),
        starting_equity=starting_equity,
        latest_equity=ending_snapshot.equity,
        return_pct=safe_return_pct(starting_equity, ending_snapshot.equity),
        cash=ending_snapshot.cash,
        market_value=ending_snapshot.market_value,
        realized_pnl=ending_snapshot.realized_pnl,
        unrealized_pnl=ending_snapshot.unrealized_pnl,
        window_started_at=window_start,
        window_ended_at=window_end,
    )


def build_paper_live_evidence(
    conn: sqlite3.Connection,
    *,
    account: AccountRecord,
    requested_strategy: str,
) -> EvaluationPaperLiveEvidence:
    account_id = account.id
    rotation_enabled = _default_book_rotation_enabled(conn, account_id)
    initial_cash = account.initial_cash
    latest_snapshot = EquitySnapshotRepository(conn).fetch_latest(account_id=account_id)
    evidence = (
        _book_strategy_evidence(
            conn,
            account=account,
            account_id=account_id,
            requested_strategy=requested_strategy,
            latest_snapshot=latest_snapshot,
        )
        if rotation_enabled
        else EvaluationPaperLiveEvidence()
    )
    if evidence.available:
        return replace(evidence, mode=_evidence_mode(account))

    if latest_snapshot is None or rotation_enabled:
        return EvaluationPaperLiveEvidence(mode=_evidence_mode(account))

    latest_equity = latest_snapshot.equity
    return EvaluationPaperLiveEvidence(
        available=True,
        mode=_evidence_mode(account),
        source_level=ACCOUNT_SNAPSHOT_SOURCE_LEVEL,
        strategy_isolated=True,
        latest_snapshot_time=latest_snapshot.snapshot_time,
        snapshot_count=EquitySnapshotRepository(conn).fetch_count(account_id=account_id),
        starting_equity=initial_cash,
        latest_equity=latest_equity,
        return_pct=safe_return_pct(initial_cash, latest_equity),
        cash=latest_snapshot.cash,
        market_value=latest_snapshot.market_value,
        realized_pnl=latest_snapshot.realized_pnl,
        unrealized_pnl=latest_snapshot.unrealized_pnl,
    )


def build_confidence(
    *,
    backtest: EvaluationBacktestEvidence,
    paper_live: EvaluationPaperLiveEvidence,
    settings: EvaluationConfidenceSettings,
) -> EvaluationConfidence:
    backtest_confidence = compute_backtest_confidence(
        trade_count=backtest.trade_count,
        snapshot_count=backtest.snapshot_count,
        settings=settings,
    )
    paper_live_confidence = compute_paper_live_confidence(
        snapshot_count=paper_live.snapshot_count,
        settings=settings,
    )
    return EvaluationConfidence(
        backtest_confidence=backtest_confidence,
        paper_live_confidence=paper_live_confidence,
        overall_confidence=compute_overall_confidence(
            backtest_confidence=backtest_confidence,
            paper_live_confidence=paper_live_confidence,
            settings=settings,
        ),
        blended_score=compute_blended_score(
            backtest_score=backtest.total_return_pct,
            paper_live_score=paper_live.return_pct,
            backtest_confidence=backtest_confidence,
            paper_live_confidence=paper_live_confidence,
            settings=settings,
        ),
    )


def build_diagnostics(
    *,
    backtest: EvaluationBacktestEvidence,
    paper_live: EvaluationPaperLiveEvidence,
    walk_forward: EvaluationWalkForwardEvidence,
    generated_at: str,
) -> EvaluationDiagnostics:
    data_gaps: list[str] = []
    if not backtest.available:
        data_gaps.append(BACKTEST_EVIDENCE_GAP)
    if not paper_live.available:
        data_gaps.append(PAPER_LIVE_EVIDENCE_GAP)
    if not walk_forward.available:
        data_gaps.append(WALK_FORWARD_EVIDENCE_GAP)
    freshness = assess_backtest_freshness(
        backtest_created_at=backtest.created_at,
        reference_iso=generated_at,
    )
    return EvaluationDiagnostics(data_gaps=data_gaps, backtest_freshness=freshness)
