from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

import pytest

from tests.support.books import assign_test_book_strategy, insert_test_book
from trading.domain.exceptions import NotFoundError, ValidationError
from trading.models.advisor import (
    DECIDED_BY_AGENT,
    DECISION_TYPE_HOLD,
    FLAG_DECISIONS_DUE,
    StrategyDecisionInsert,
)
from trading.repositories.snapshots import EquitySnapshotRepository
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


def test_record_freezes_book_state_strategy_evidence_and_notes(conn, account) -> None:
    decision_id = _record_hold(conn, notes={"source": "digest"})

    record = StrategyDecisionRepository(conn).fetch(strategy_decision_id=decision_id)
    evidence = json.loads(record.evidence_json)
    assert evidence["notes"] == {"source": "digest"}
    assert (evidence["book"]["book_name"], evidence["book"]["strategy_key"]) == ("default", "trend")
    assert evidence["strategy"]["key"] == "trend"
    assert "walk_forward" in evidence["strategy"]
    # Account-level paper and confidence figures are not frozen: for a sleeve they describe the roll-up.
    assert "paper_live" not in json.dumps(evidence)
    assert "missing_paper_live_evidence" not in evidence["strategy"]["data_gaps"]


def test_a_sleeve_decision_freezes_the_sleeves_own_paper_return(conn, account) -> None:
    sleeve_id = insert_test_book(conn, account_id=account.id, name="sleeve")
    assign_test_book_strategy(conn, book_id=sleeve_id, strategy_name="rsi", now_iso="2026-09-01T00:00:00Z")
    snapshots = EquitySnapshotRepository(conn)
    for when, equity in (("2026-09-02T00:00:00Z", 10_000), ("2026-09-30T00:00:00Z", 9_500)):
        snapshots.insert_for_book(
            book_id=sleeve_id,
            snapshot_time=when,
            cash=Decimal(equity),
            market_value=Decimal(0),
            equity=Decimal(equity),
            realized_pnl=Decimal(0),
            unrealized_pnl=Decimal(0),
        )

    decision_id = _record_hold(conn, book_name="sleeve", strategy_key="rsi")

    record = StrategyDecisionRepository(conn).fetch(strategy_decision_id=decision_id)
    book = json.loads(record.evidence_json)["book"]
    assert (book["book_name"], book["strategy_key"], book["paper_snapshot_count"]) == ("sleeve", "rsi", 2)
    assert book["paper_return_pct"] == pytest.approx(-5.0)


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


def _default_book_digest(digest):
    (account_digest,) = digest.accounts
    return next(book for book in account_digest.books if book.is_default)


def test_digest_flags_a_decision_whose_window_has_closed(conn, account) -> None:
    book = get_default_book(conn, account_id=account.id)
    StrategyDecisionRepository(conn).insert(
        StrategyDecisionInsert(
            account_id=account.id,
            book_id=book.id,
            decision_type=DECISION_TYPE_HOLD,
            rationale="old hold",
            evidence_json="{}",
            decided_by=DECIDED_BY_AGENT,
            created_at="2026-08-03T00:00:00Z",
        )
    )

    digest = build_advisor_digest(conn, account_name=_ACCOUNT, as_of=date(2026, 10, 1))

    book_digest = _default_book_digest(digest)
    assert [record.rationale for record in book_digest.due_decisions] == ["old hold"]
    assert FLAG_DECISIONS_DUE in [flag.code for flag in book_digest.flags]


def test_digest_reviews_every_book_with_its_own_decisions_and_paper(conn, account) -> None:
    sleeve_id = insert_test_book(conn, account_id=account.id, name="sleeve")
    assign_test_book_strategy(conn, book_id=sleeve_id, strategy_name="rsi", now_iso="2026-09-01T00:00:00Z")
    snapshots = EquitySnapshotRepository(conn)
    for when, equity in (
        ("2026-08-15T00:00:00Z", 9_000),
        ("2026-09-02T00:00:00Z", 10_000),
        ("2026-09-30T00:00:00Z", 11_000),
    ):
        snapshots.insert_for_book(
            book_id=sleeve_id,
            snapshot_time=when,
            cash=Decimal(equity),
            market_value=Decimal(0),
            equity=Decimal(equity),
            realized_pnl=Decimal(0),
            unrealized_pnl=Decimal(0),
        )
    _record_hold(conn, book_name="sleeve", strategy_key="rsi")

    digest = build_advisor_digest(conn, account_name=_ACCOUNT, as_of=date(2026, 10, 1))

    (account_digest,) = digest.accounts
    sleeve = next(book for book in account_digest.books if book.book_name == "sleeve")
    default = next(book for book in account_digest.books if book.is_default)
    assert sleeve.strategy_key == "rsi"
    # Measured from the snapshot at or after the 2026-09-01 assignment, not the earlier one.
    assert sleeve.evidence.paper_return_pct == pytest.approx(10.0)
    assert sleeve.evidence.paper_snapshot_count == 2
    assert len(sleeve.recent_decisions) == 1
    assert default.recent_decisions == []


def test_digest_covers_every_account_and_renders(conn, account) -> None:
    create_account(conn, "advisor_other", "trend", 5_000.0, "SPY")
    _record_hold(conn)

    digest = build_advisor_digest(conn, as_of=date(2026, 10, 1))
    lines = render_advisor_digest_lines(digest)

    assert {item.account_name for item in digest.accounts} == {_ACCOUNT, "advisor_other"}
    assert any(line.startswith(f"== {_ACCOUNT} ==") for line in lines)
    assert any(line.startswith("-- book default (default): trend") for line in lines)
    assert any("hold by agent" in line for line in lines)


def test_scoring_lines_show_the_verdict_or_the_reason() -> None:
    from trading.models.advisor import DecisionScoreResult, StrategyDecisionOutcome
    from trading.services.advisor.presentation import render_scoring_lines

    measured = DecisionScoreResult(
        strategy_decision_id=1,
        account_name=_ACCOUNT,
        decision_type="hold",
        outcome=StrategyDecisionOutcome(
            outcome_status="measured",
            outcome_window_start="2026-08-03",
            outcome_window_end="2026-09-01",
            chosen_return_pct=4.0,
            alternative_return_pct=1.0,
            outcome_verdict="helped",
            outcome_note="chosen a vs rejected b",
        ),
    )
    inconclusive = DecisionScoreResult(
        strategy_decision_id=2,
        account_name=_ACCOUNT,
        decision_type="run_experiment",
        outcome=StrategyDecisionOutcome(outcome_status="inconclusive", outcome_note="nothing to compare"),
    )

    lines = render_scoring_lines([measured, inconclusive])

    assert lines[0] == "Scored 2 decision(s):"
    assert "helped | chosen 4.00% vs rejected 1.00% over 2026-08-03..2026-09-01" in lines[1]
    assert lines[2].endswith("inconclusive (nothing to compare)")


def test_scorecard_groups_scored_decisions_and_rejects_an_unknown_grouping(conn, account) -> None:
    from trading.models.advisor import StrategyDecisionOutcome
    from trading.services.advisor.presentation import render_scorecard_lines
    from trading.services.advisor.scorecard import build_advisor_scorecard

    decision_id = _record_hold(conn)
    StrategyDecisionRepository(conn).update_outcome(
        strategy_decision_id=decision_id,
        outcome=StrategyDecisionOutcome(
            outcome_status="measured",
            outcome_verdict="helped",
            chosen_return_pct=3.0,
            alternative_return_pct=1.0,
            realized_benchmark_return_pct=-2.0,
            outcome_measured_at="2026-10-01T00:00:00Z",
        ),
    )
    _record_hold(conn)  # still pending: not on the scorecard

    scorecard = build_advisor_scorecard(conn, account_name=_ACCOUNT)
    lines = render_scorecard_lines(scorecard)

    (group,) = scorecard.groups
    assert (group.key, group.scored_count, group.points) == (DECIDED_BY_AGENT, 1, 1)
    assert group.points_by_regime["down"] == 1
    assert scorecard.leader is None
    assert any("insufficient decisions (1 of 20)" in line for line in lines)
    with pytest.raises(ValidationError, match="Unknown scorecard grouping"):
        build_advisor_scorecard(conn, group_by="mood")


def test_scorecard_without_scored_decisions_says_so(conn, account) -> None:
    from trading.services.advisor.presentation import render_scorecard_lines
    from trading.services.advisor.scorecard import build_advisor_scorecard

    lines = render_scorecard_lines(build_advisor_scorecard(conn))
    assert lines[-1] == "No scored decisions yet."
