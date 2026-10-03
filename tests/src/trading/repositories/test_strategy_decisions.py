from __future__ import annotations

import sqlite3

import pytest

from tests.support.repositories import insert_repository_account
from trading.models.advisor import (
    DECIDED_BY_AGENT,
    DECISION_TYPE_HOLD,
    DEFAULT_OUTCOME_WINDOW_DAYS,
    OUTCOME_STATUS_MEASURED,
    OUTCOME_STATUS_PENDING,
    OUTCOME_VERDICT_HELPED,
    StrategyDecisionInsert,
    StrategyDecisionOutcome,
)
from trading.repositories.strategy_decisions import StrategyDecisionRepository


def _insert(conn, *, account_id: int, created_at: str, rationale: str = "evidence is stale") -> int:
    return StrategyDecisionRepository(conn).insert(
        StrategyDecisionInsert(
            account_id=account_id,
            decision_type=DECISION_TYPE_HOLD,
            rationale=rationale,
            evidence_json='{"freshness": "stale"}',
            optimization_experiment_id=42,
            decided_by=DECIDED_BY_AGENT,
            created_at=created_at,
        )
    )


def test_insert_round_trips_and_starts_pending(conn) -> None:
    account_id = insert_repository_account(conn, name="acct_decisions_roundtrip")
    decision_id = _insert(conn, account_id=account_id, created_at="2026-10-01T00:00:00Z")

    record = StrategyDecisionRepository(conn).fetch(strategy_decision_id=decision_id)

    assert record is not None
    assert record.decision_type == DECISION_TYPE_HOLD
    assert record.optimization_experiment_id == 42
    assert record.outcome_window_days == DEFAULT_OUTCOME_WINDOW_DAYS
    assert record.outcome.outcome_status == OUTCOME_STATUS_PENDING
    assert record.outcome.outcome_verdict is None


def test_update_outcome_writes_only_the_outcome(conn) -> None:
    account_id = insert_repository_account(conn, name="acct_decisions_outcome")
    decision_id = _insert(conn, account_id=account_id, created_at="2026-10-01T00:00:00Z")
    repository = StrategyDecisionRepository(conn)

    updated = repository.update_outcome(
        strategy_decision_id=decision_id,
        outcome=StrategyDecisionOutcome(
            outcome_status=OUTCOME_STATUS_MEASURED,
            outcome_window_start="2026-10-01",
            outcome_window_end="2026-10-30",
            realized_return_pct=2.5,
            realized_benchmark_return_pct=1.0,
            outcome_verdict=OUTCOME_VERDICT_HELPED,
            outcome_measured_at="2026-10-31T00:00:00Z",
        ),
    )

    record = repository.fetch(strategy_decision_id=decision_id)
    assert updated is True
    assert record is not None
    assert record.outcome.outcome_verdict == OUTCOME_VERDICT_HELPED
    assert record.outcome.realized_return_pct == 2.5
    assert record.rationale == "evidence is stale"


def test_update_outcome_reports_a_missing_row(conn) -> None:
    updated = StrategyDecisionRepository(conn).update_outcome(
        strategy_decision_id=999_999,
        outcome=StrategyDecisionOutcome(outcome_status=OUTCOME_STATUS_PENDING),
    )
    assert updated is False


def test_decision_columns_cannot_be_rewritten_through_sql(conn) -> None:
    account_id = insert_repository_account(conn, name="acct_decisions_write_once")
    decision_id = _insert(conn, account_id=account_id, created_at="2026-10-01T00:00:00Z")
    with pytest.raises(sqlite3.IntegrityError, match="write-once"):
        conn.execute("UPDATE strategy_decisions SET rationale = 'revised' WHERE id = ?", (decision_id,))


def test_fetch_recent_is_newest_first(conn) -> None:
    account_id = insert_repository_account(conn, name="acct_decisions_recent")
    _insert(conn, account_id=account_id, created_at="2026-09-01T00:00:00Z", rationale="older")
    _insert(conn, account_id=account_id, created_at="2026-10-01T00:00:00Z", rationale="newer")

    records = StrategyDecisionRepository(conn).fetch_recent(account_id=account_id)

    assert [record.rationale for record in records] == ["newer", "older"]


def test_fetch_pending_skips_scored_rows_and_filters_by_account(conn) -> None:
    first = insert_repository_account(conn, name="acct_decisions_pending_a")
    second = insert_repository_account(conn, name="acct_decisions_pending_b")
    scored = _insert(conn, account_id=first, created_at="2026-09-01T00:00:00Z", rationale="scored")
    _insert(conn, account_id=first, created_at="2026-09-02T00:00:00Z", rationale="open_a")
    _insert(conn, account_id=second, created_at="2026-09-03T00:00:00Z", rationale="open_b")
    repository = StrategyDecisionRepository(conn)
    repository.update_outcome(
        strategy_decision_id=scored,
        outcome=StrategyDecisionOutcome(outcome_status="inconclusive", outcome_note="no snapshots"),
    )

    assert [record.rationale for record in repository.fetch_pending()] == ["open_a", "open_b"]
    assert [record.rationale for record in repository.fetch_pending(account_id=second)] == ["open_b"]


def test_fetch_scored_returns_measured_and_inconclusive_but_not_pending(conn) -> None:
    first = insert_repository_account(conn, name="acct_decisions_scored_a")
    second = insert_repository_account(conn, name="acct_decisions_scored_b")
    repository = StrategyDecisionRepository(conn)
    measured = _insert(conn, account_id=first, created_at="2026-09-01T00:00:00Z", rationale="measured")
    inconclusive = _insert(conn, account_id=second, created_at="2026-09-02T00:00:00Z", rationale="inconclusive")
    _insert(conn, account_id=first, created_at="2026-09-03T00:00:00Z", rationale="pending")
    repository.update_outcome(
        strategy_decision_id=measured,
        outcome=StrategyDecisionOutcome(
            outcome_status=OUTCOME_STATUS_MEASURED,
            outcome_verdict=OUTCOME_VERDICT_HELPED,
            outcome_measured_at="2026-10-01T00:00:00Z",
        ),
    )
    repository.update_outcome(
        strategy_decision_id=inconclusive,
        outcome=StrategyDecisionOutcome(outcome_status="inconclusive", outcome_note="no alternative"),
    )

    assert [record.rationale for record in repository.fetch_scored()] == ["measured", "inconclusive"]
    assert [record.rationale for record in repository.fetch_scored(account_id=first)] == ["measured"]
