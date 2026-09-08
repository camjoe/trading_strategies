from __future__ import annotations

import sqlite3

import pytest

from tests.support.repositories import insert_repository_account
from trading.models.books import RiskDecisionInsert, RiskSnapshotInsert
from trading.repositories.books import BookRepository
from trading.repositories.risk import RiskDecisionRepository, RiskSnapshotRepository


def _insert_decision(
    conn, *, account_id: int, decision_time: str, reason_code: str, book_id: int | None = None
) -> int:
    return RiskDecisionRepository(conn).insert(
        RiskDecisionInsert(
            account_id=account_id,
            book_id=book_id,
            decision_time=decision_time,
            symbol="AAPL",
            side="buy",
            action="block",
            reason_code=reason_code,
            requested_qty=10,
            approved_qty=0,
            requested_notional=1000.0,
            approved_notional=0.0,
            risk_payload_json="{}",
            created_at=decision_time,
        )
    )


def test_risk_decisions_insert_and_fetch_recent(conn) -> None:
    account_id = insert_repository_account(conn, name="acct_risk_recent")
    _insert_decision(conn, account_id=account_id, decision_time="2026-05-03T10:00:00Z", reason_code="older")
    _insert_decision(conn, account_id=account_id, decision_time="2026-05-04T10:00:00Z", reason_code="newer")

    records = RiskDecisionRepository(conn).fetch_recent(account_id=account_id, limit=10)

    assert [r.reason_code for r in records] == ["newer", "older"]
    assert records[0].account_id == account_id
    assert records[0].book_id is None


def test_risk_decisions_fetch_for_account_date_windows_by_day(conn) -> None:
    account_id = insert_repository_account(conn, name="acct_risk_date")
    _insert_decision(conn, account_id=account_id, decision_time="2026-05-03T09:00:00Z", reason_code="in_window")
    _insert_decision(conn, account_id=account_id, decision_time="2026-05-04T00:00:00Z", reason_code="next_day")

    records = RiskDecisionRepository(conn).fetch_for_account_date(account_id=account_id, report_date="2026-05-03")

    assert [r.reason_code for r in records] == ["in_window"]


def test_risk_decisions_enforce_book_account_relationship(conn) -> None:
    book_account_id = insert_repository_account(conn, name="acct_risk_book")
    other_account_id = insert_repository_account(conn, name="acct_risk_other")
    book_id = BookRepository(conn).insert(
        account_id=book_account_id,
        name="risk-book",
        is_default=0,
        start_equity=1000.0,
        current_cash=1000.0,
        current_equity=1000.0,
        created_at="2026-05-03T10:00:00Z",
        updated_at="2026-05-03T10:00:00Z",
    )

    with pytest.raises(sqlite3.IntegrityError):
        _insert_decision(
            conn,
            account_id=other_account_id,
            book_id=book_id,
            decision_time="2026-05-03T10:00:00Z",
            reason_code="mismatched_book",
        )

    decision_id = _insert_decision(
        conn,
        account_id=other_account_id,
        book_id=None,
        decision_time="2026-05-03T10:01:00Z",
        reason_code="account_level",
    )
    assert decision_id > 0


def test_risk_snapshots_insert_and_fetch_latest(conn) -> None:
    account_id = insert_repository_account(conn, name="acct_risk_snap")
    repo = RiskSnapshotRepository(conn)
    repo.insert(
        RiskSnapshotInsert(
            account_id=account_id,
            snapshot_time="2026-05-03T10:00:00Z",
            gross_exposure=100.0,
            net_exposure=100.0,
            max_symbol_concentration_pct=0.1,
            max_sector_concentration_pct=0.2,
            kill_switch_triggered=0,
        )
    )
    repo.insert(
        RiskSnapshotInsert(
            account_id=account_id,
            snapshot_time="2026-05-04T10:00:00Z",
            gross_exposure=200.0,
            net_exposure=150.0,
            max_symbol_concentration_pct=0.3,
            max_sector_concentration_pct=0.4,
            kill_switch_triggered=1,
            risk_payload_json='{"k": 1}',
        )
    )

    latest = repo.fetch_latest(account_id=account_id)

    assert latest is not None
    assert latest.snapshot_time == "2026-05-04T10:00:00Z"
    assert latest.gross_exposure == 200.0
    assert latest.kill_switch_triggered == 1
