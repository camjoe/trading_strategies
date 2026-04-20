from __future__ import annotations

from trading.domain.evaluation_models import EvaluationBasicScope, EvaluationConfidence, StrategyEvaluationArtifact
from trading.domain.promotion_models import PromotionAssessment
from trading.repositories.promotion_repository import (
    fetch_open_promotion_review,
    fetch_promotion_review_by_id,
    fetch_promotion_review_events,
    fetch_promotion_reviews_for_account,
    insert_promotion_review,
    insert_promotion_review_event,
    update_promotion_review_record,
)


def _evaluation(*, account_id: int = 1, account_name: str = "acct_a", strategy_name: str = "Trend") -> StrategyEvaluationArtifact:
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


def _insert_account(conn) -> None:
    conn.execute(
        """
        INSERT INTO accounts (id, name, strategy, initial_cash, benchmark_ticker, created_at)
        VALUES (1, 'acct_a', 'Trend', 1000, 'SPY', '2026-01-01T00:00:00Z')
        """
    )
    conn.commit()


def test_insert_and_fetch_promotion_review_round_trip(conn) -> None:
    _insert_account(conn)

    review = insert_promotion_review(
        conn,
        assessment=_assessment(),
        evaluation=_evaluation(),
        requested_by="alice",
        operator_summary_note="initial request",
        created_at="2026-03-01T00:00:00Z",
    )

    fetched = fetch_promotion_review_by_id(conn, review_id=int(review.id))

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
    _insert_account(conn)
    review = insert_promotion_review(
        conn,
        assessment=_assessment(),
        evaluation=_evaluation(),
        requested_by="alice",
        operator_summary_note=None,
        created_at="2026-03-01T00:00:00Z",
    )

    first = insert_promotion_review_event(
        conn,
        review_id=int(review.id),
        event_type="requested",
        actor_name="alice",
        from_review_state=None,
        to_review_state="requested",
        note="requested",
        event_payload={"ready_for_live": True},
        created_at="2026-03-01T00:00:00Z",
    )
    second = insert_promotion_review_event(
        conn,
        review_id=int(review.id),
        event_type="note_added",
        actor_name="bob",
        from_review_state="requested",
        to_review_state="requested",
        note="needs more context",
        event_payload={},
        created_at="2026-03-01T00:10:00Z",
    )

    events = fetch_promotion_review_events(conn, review_id=int(review.id))

    assert first.event_seq == 1
    assert second.event_seq == 2
    assert [event.event_seq for event in events] == [1, 2]
    assert events[1].note == "needs more context"


def test_fetch_open_history_and_update_review_state(conn) -> None:
    _insert_account(conn)
    review = insert_promotion_review(
        conn,
        assessment=_assessment(),
        evaluation=_evaluation(),
        requested_by="alice",
        operator_summary_note=None,
        created_at="2026-03-01T00:00:00Z",
    )

    open_review = fetch_open_promotion_review(conn, account_id=1, strategy_name="Trend")
    assert open_review is not None
    assert open_review.id == review.id

    updated = update_promotion_review_record(
        conn,
        review_id=int(review.id),
        review_state="approved",
        reviewed_by="reviewer",
        operator_summary_note="looks good",
        updated_at="2026-03-01T01:00:00Z",
        closed_at="2026-03-01T01:00:00Z",
    )

    assert updated.review_state == "approved"
    assert updated.reviewed_by == "reviewer"
    assert fetch_open_promotion_review(conn, account_id=1, strategy_name="Trend") is None
    history = fetch_promotion_reviews_for_account(conn, account_id=1, strategy_name="Trend", limit=10)
    assert [item.review_state for item in history] == ["approved"]
