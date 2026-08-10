"""Execution-owned risk-audit persistence for one book run.

``risk.py`` keeps its persistence helpers dependency-injected (repository
callables passed in) so it stays free of repository imports. This module owns
that wiring and exposes the single operation callers need: persist a run's
normalized risk decisions plus its account risk snapshot.
"""

from __future__ import annotations

import sqlite3

from trading.models.execution import BookRunAudit
from trading.repositories.books import BookRepository
from trading.repositories.positions import PositionRepository
from trading.repositories.risk import RiskDecisionRepository, RiskSnapshotRepository
from trading.repositories.snapshots import EquitySnapshotRepository
from trading.services.books.sector_config import load_symbol_sector_map
from trading.services.execution.risk import (
    persist_book_risk_snapshot,
    persist_normalized_risk_decisions,
)


def persist_book_run_audit(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    snapshot_time: str,
    audit: BookRunAudit,
) -> None:
    """Persist one book run's risk audit: normalized decisions, then the snapshot."""
    persist_normalized_risk_decisions(
        conn,
        account_id=account_id,
        decision_time=snapshot_time,
        risk_decisions=audit.risk_decisions,
        insert_risk_decision_fn=lambda c, decision: RiskDecisionRepository(c).insert(decision),
    )
    # Exposure is sourced from the clean book positions/equity (the submission path's
    # source of truth); persisted to the account-keyed risk_snapshots table.
    persist_book_risk_snapshot(
        conn,
        account_id=account_id,
        snapshot_time=snapshot_time,
        kill_switch_triggered=bool(audit.kill_switch_reasons),
        payload={
            "kill_switch_reasons": audit.kill_switch_reasons,
            "risk_decisions": audit.risk_decisions,
            "summary": audit.summary(),
        },
        fetch_positions_for_account_fn=lambda c, *, account_id: PositionRepository(c).fetch_for_account(
            account_id=account_id
        ),
        fetch_books_for_account_fn=lambda c, *, account_id: BookRepository(c).fetch_for_account(account_id=account_id),
        fetch_max_equity_fn=lambda c, *, account_id: EquitySnapshotRepository(c).fetch_max_equity(
            account_id=account_id
        ),
        insert_risk_snapshot_fn=RiskSnapshotRepository(conn).insert,
        symbol_sector_map=load_symbol_sector_map(),
    )
