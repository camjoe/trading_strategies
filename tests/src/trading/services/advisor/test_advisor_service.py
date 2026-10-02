from __future__ import annotations

import json
from datetime import date

import pytest

from trading.domain.exceptions import NotFoundError, ValidationError
from trading.models.advisor import (
    DECIDED_BY_AGENT,
    DECISION_TYPE_HOLD,
    FLAG_DECISIONS_DUE,
    StrategyDecisionInsert,
)
from trading.repositories.strategy_decisions import StrategyDecisionRepository
from trading.services.accounts.mutations import create_account, get_account
from trading.services.advisor.decisions import record_decision
from trading.services.advisor.digest import build_advisor_digest
from trading.services.advisor.presentation import render_advisor_digest_lines
from trading.services.books.book_assignments import get_default_book, open_assignment_for_book

_ACCOUNT = "advisor_acct"


@pytest.fixture
def account(conn):
    create_account(conn, _ACCOUNT, "trend", 10_000.0, "SPY")
    return get_account(conn, _ACCOUNT)


def _record_hold(conn, **overrides) -> int:
    arguments = dict(
        account_name=_ACCOUNT,
        decision_type=DECISION_TYPE_HOLD,
        rationale="walk-forward evidence is stale; waiting for a fresh sweep",
        decided_by=DECIDED_BY_AGENT,
    )
    arguments.update(overrides)
    return record_decision(conn, **arguments)


def test_record_defaults_to_the_default_book_and_its_assigned_strategy(conn, account) -> None:
    decision_id = _record_hold(conn, notes={"source": "digest"})

    record = StrategyDecisionRepository(conn).fetch(strategy_decision_id=decision_id)
    book = get_default_book(conn, account_id=account.id)
    assignment = open_assignment_for_book(conn, book_id=book.id)
    assert record is not None
    assert record.book_id == book.id
    assert record.strategy_id == assignment.strategy_id
    assert record.outcome.outcome_status == "pending"


def test_record_freezes_the_evaluation_alongside_the_notes(conn, account) -> None:
    decision_id = _record_hold(conn, notes={"source": "digest"})

    record = StrategyDecisionRepository(conn).fetch(strategy_decision_id=decision_id)
    evidence = json.loads(record.evidence_json)
    assert evidence["notes"] == {"source": "digest"}
    assert evidence["evaluation"]["basic"]["account_name"] == _ACCOUNT


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"decision_type": "yolo"}, "Unknown decision_type"),
        ({"rationale": "   "}, "needs a rationale"),
        ({"decided_by": ""}, "decided_by"),
        ({"outcome_window_days": 0}, "positive"),
        ({"notes": {"bad": object()}}, "JSON-serializable"),
    ],
)
def test_record_rejects_invalid_input(conn, account, overrides, message) -> None:
    with pytest.raises(ValidationError, match=message):
        _record_hold(conn, **overrides)


def test_record_rejects_unknown_book_and_strategy(conn, account) -> None:
    with pytest.raises(NotFoundError):
        _record_hold(conn, book_name="no_such_book")
    with pytest.raises(NotFoundError):
        _record_hold(conn, strategy_key="no_such_strategy")


def test_digest_flags_a_decision_whose_window_has_closed(conn, account) -> None:
    StrategyDecisionRepository(conn).insert(
        StrategyDecisionInsert(
            account_id=account.id,
            decision_type=DECISION_TYPE_HOLD,
            rationale="old hold",
            evidence_json="{}",
            decided_by=DECIDED_BY_AGENT,
            created_at="2026-08-03T00:00:00Z",
        )
    )

    digest = build_advisor_digest(conn, account_name=_ACCOUNT, as_of=date(2026, 10, 1))

    (account_digest,) = digest.accounts
    assert [record.rationale for record in account_digest.due_decisions] == ["old hold"]
    assert FLAG_DECISIONS_DUE in [flag.code for flag in account_digest.flags]


def test_digest_covers_every_account_and_renders(conn, account) -> None:
    create_account(conn, "advisor_other", "trend", 5_000.0, "SPY")
    _record_hold(conn)

    digest = build_advisor_digest(conn, as_of=date(2026, 10, 1))
    lines = render_advisor_digest_lines(digest)

    assert {item.account_name for item in digest.accounts} == {_ACCOUNT, "advisor_other"}
    assert f"== {_ACCOUNT} ==" in lines
    assert any("hold by agent" in line for line in lines)
