from __future__ import annotations

import pytest

from trading.domain.evaluation_models import EvaluationBasicScope, EvaluationConfidence, StrategyEvaluationArtifact
from trading.domain.promotion_models import PromotionAssessment
from trading.repositories.promotion import PromotionReviewRepository, _row_json_object
from tests.support.repositories import insert_repository_account


class _StaticCursor:
    def __init__(self, *, lastrowid=None, row=None) -> None:
        self.lastrowid = lastrowid
        self._row = row

    def fetchone(self):
        return self._row


class _StaticConnection:
    def __init__(self, *results) -> None:
        self._results = list(results)

    def execute(self, *_args, **_kwargs):
        if not self._results:
            raise AssertionError("Unexpected execute call")
        return self._results.pop(0)


def _evaluation(
    *, account_id: int = 1, account_name: str = "acct_a", strategy_name: str = "Trend"
) -> StrategyEvaluationArtifact:
    return StrategyEvaluationArtifact(
        basic=EvaluationBasicScope(
            account_id=account_id,
            account_name=account_name,
            requested_strategy=strategy_name,
            live_trading_enabled=False,
        ),
        confidence=EvaluationConfidence(overall_confidence=0.82),
    )


def _assessment(*, account_name: str = "acct_a", strategy_name: str = "Trend") -> PromotionAssessment:
    return PromotionAssessment(
        account_name=account_name,
        strategy_name=strategy_name,
        stage="promotion_review",
        status="ready_for_review",
        ready_for_live=True,
        overall_confidence=0.82,
        next_action="Request operator review.",
    )


def test_insert_and_fetch_promotion_review_round_trip(conn) -> None:
    account_id = insert_repository_account(conn, name="acct_a", strategy="Trend", initial_cash=1000.0)
    repo = PromotionReviewRepository(conn)

    review = repo.insert_review(
        assessment=_assessment(account_name="acct_a", strategy_name="Trend"),
        evaluation=_evaluation(account_id=account_id, account_name="acct_a", strategy_name="Trend"),
        requested_by="alice",
        operator_summary_note="initial request",
        created_at="2026-03-01T00:00:00Z",
    )

    fetched = repo.fetch_by_id(review_id=int(review.id))

    assert fetched is not None
    assert fetched.account_name_snapshot == "acct_a"
    assert fetched.strategy_name == "Trend"
    assert fetched.review_state == "requested"
    assert fetched.ready_for_live is True
    assert fetched.requested_by == "alice"
    assert fetched.operator_summary_note == "initial request"
    assert fetched.frozen_assessment_payload["status"] == "ready_for_review"
    assert fetched.frozen_evaluation_payload["basic"]["account_name"] == "acct_a"


def test_insert_promotion_review_event_sequences_per_review(conn) -> None:
    account_id = insert_repository_account(conn, name="acct_a", strategy="Trend", initial_cash=1000.0)
    repo = PromotionReviewRepository(conn)
    review = repo.insert_review(
        assessment=_assessment(account_name="acct_a", strategy_name="Trend"),
        evaluation=_evaluation(account_id=account_id, account_name="acct_a", strategy_name="Trend"),
        requested_by="alice",
        operator_summary_note=None,
        created_at="2026-03-01T00:00:00Z",
    )

    first = repo.insert_event(
        review_id=int(review.id),
        event_type="requested",
        actor_name="alice",
        from_review_state=None,
        to_review_state="requested",
        note="requested",
        event_payload={"ready_for_live": True},
        created_at="2026-03-01T00:00:00Z",
    )
    second = repo.insert_event(
        review_id=int(review.id),
        event_type="note_added",
        actor_name="bob",
        from_review_state="requested",
        to_review_state="requested",
        note="needs more context",
        event_payload={},
        created_at="2026-03-01T00:10:00Z",
    )

    events = repo.fetch_events(review_id=int(review.id))

    assert first.event_seq == 1
    assert second.event_seq == 2
    assert [event.event_seq for event in events] == [1, 2]
    assert events[1].note == "needs more context"


def test_fetch_open_history_and_update_review_state(conn) -> None:
    account_id = insert_repository_account(conn, name="acct_a", strategy="Trend", initial_cash=1000.0)
    repo = PromotionReviewRepository(conn)
    review = repo.insert_review(
        assessment=_assessment(account_name="acct_a", strategy_name="Trend"),
        evaluation=_evaluation(account_id=account_id, account_name="acct_a", strategy_name="Trend"),
        requested_by="alice",
        operator_summary_note=None,
        created_at="2026-03-01T00:00:00Z",
    )

    open_review = repo.fetch_open(account_id=1, strategy_name="Trend")
    assert open_review is not None
    assert open_review.id == review.id

    updated = repo.update_review(
        review_id=int(review.id),
        review_state="approved",
        reviewed_by="reviewer",
        operator_summary_note="looks good",
        updated_at="2026-03-01T01:00:00Z",
        closed_at="2026-03-01T01:00:00Z",
    )

    assert updated.review_state == "approved"
    assert updated.reviewed_by == "reviewer"
    assert repo.fetch_open(account_id=1, strategy_name="Trend") is None
    history = repo.fetch_for_account(account_id=1, strategy_name="Trend", limit=10)
    assert [item.review_state for item in history] == ["approved"]


def test_row_json_and_require_helpers_raise_on_invalid_payloads(monkeypatch) -> None:
    assert _row_json_object({"payload": None}, "payload") == {}

    with pytest.raises(ValueError, match="Expected JSON object in column 'payload'"):
        _row_json_object({"payload": "[1, 2, 3]"}, "payload")

    monkeypatch.setattr(PromotionReviewRepository, "fetch_by_id", lambda self, *, review_id: None)
    with pytest.raises(ValueError, match="Promotion review 7 not found after update"):
        PromotionReviewRepository(object())._require_review(review_id=7, context="update")

    with pytest.raises(ValueError, match="Promotion review event 3 not found after insert"):
        PromotionReviewRepository(
            _StaticConnection(_StaticCursor(row=None))
        )._require_event(event_id=3)


@pytest.mark.parametrize(
    ("evaluation", "message"),
    [
        (_evaluation(account_id=None), "Promotion review requires evaluation.basic.account_id."),
        (_evaluation(account_name=None), "Promotion review requires evaluation.basic.account_name."),
        (_evaluation(strategy_name=None), "Promotion review requires evaluation.basic.requested_strategy."),
    ],
)
def test_insert_promotion_review_validates_required_evaluation_fields(evaluation, message) -> None:
    with pytest.raises(ValueError, match=message):
        PromotionReviewRepository(_StaticConnection()).insert_review(
            assessment=_assessment(),
            evaluation=evaluation,
            requested_by=None,
            operator_summary_note=None,
            created_at="2026-03-01T00:00:00Z",
        )


def test_insert_promotion_review_guard_paths_raise_when_ids_cannot_be_materialized() -> None:
    with pytest.raises(ValueError, match="Expected integer promotion review id after insert"):
        PromotionReviewRepository(_StaticConnection(_StaticCursor(lastrowid=None))).insert_review(
            assessment=_assessment(),
            evaluation=_evaluation(),
            requested_by="alice",
            operator_summary_note=None,
            created_at="2026-03-01T00:00:00Z",
        )

    with pytest.raises(ValueError, match="Unable to compute next event sequence for review 1"):
        PromotionReviewRepository(_StaticConnection(_StaticCursor(row=None))).insert_event(
            review_id=1,
            event_type="requested",
            actor_name="alice",
            from_review_state=None,
            to_review_state="requested",
            note=None,
            event_payload={},
            created_at="2026-03-01T00:00:00Z",
        )

    with pytest.raises(ValueError, match="Expected integer promotion review event id after insert"):
        PromotionReviewRepository(
            _StaticConnection(_StaticCursor(row={"next_seq": 1}), _StaticCursor(lastrowid=None))
        ).insert_event(
            review_id=1,
            event_type="requested",
            actor_name="alice",
            from_review_state=None,
            to_review_state="requested",
            note=None,
            event_payload={},
            created_at="2026-03-01T00:00:00Z",
        )
