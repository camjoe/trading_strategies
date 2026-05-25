import pytest

from trading.services.promotion import (
    execute_promotion_review_action,
    execute_promotion_review_request,
    fetch_promotion_review_history,
)
from trading.services.promotion import actions as promotion_actions
from tests.support.promotion import make_ready_evaluation


def _ready_assessment(*, account_name: str = "acct_service", strategy_name: str = "trend_v1"):
    return promotion_actions.PromotionAssessment(
        account_name=account_name,
        strategy_name=strategy_name,
        stage="promotion_review",
        status="ready",
        ready_for_live=True,
    )


def test_execute_promotion_review_request_persists_frozen_snapshot(
    conn,
    promotion_account: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        promotion_actions,
        "_fetch_current_promotion_snapshot",
        lambda _conn, *, account_name, strategy_name=None: (
            make_ready_evaluation(
                account_name=account_name,
                strategy_name=strategy_name or "trend_v1",
            ),
            _ready_assessment(
                account_name=account_name,
                strategy_name=strategy_name or "trend_v1",
            ),
        ),
    )

    review = execute_promotion_review_request(
        conn,
        account_name="acct_service",
        strategy_name="trend_v1",
        requested_by="cam",
        note="please review",
    )

    assert review.account_name_snapshot == "acct_service"
    assert review.review_state == "requested"
    assert review.requested_by == "cam"
    assert review.ready_for_live is True

    entries = fetch_promotion_review_history(conn, account_name="acct_service")
    assert len(entries) == 1
    assert entries[0].events[0].event_type == "requested"
    assert entries[0].events[0].note == "please review"


def test_execute_promotion_review_action_closes_open_review(
    conn,
    promotion_account: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        promotion_actions,
        "_fetch_current_promotion_snapshot",
        lambda _conn, *, account_name, strategy_name=None: (
            make_ready_evaluation(
                account_name=account_name,
                strategy_name=strategy_name or "trend_v1",
            ),
            _ready_assessment(
                account_name=account_name,
                strategy_name=strategy_name or "trend_v1",
            ),
        ),
    )
    review = execute_promotion_review_request(conn, account_name="acct_service", requested_by="cam")

    updated = execute_promotion_review_action(
        conn,
        review_id=int(review.id),
        action="approve",
        actor_name="reviewer",
        note="approved for manual promotion",
    )

    assert updated.review_state == "approved"
    assert updated.reviewed_by == "reviewer"
    assert updated.closed_at is not None


def test_execute_promotion_review_request_canonicalizes_strategy_for_open_review_dedup(
    conn,
    promotion_account: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        promotion_actions,
        "_fetch_current_promotion_snapshot",
        lambda _conn, *, account_name, strategy_name=None: (
            make_ready_evaluation(
                account_name=account_name,
                strategy_name=strategy_name or "trend",
            ),
            _ready_assessment(
                account_name=account_name,
                strategy_name=strategy_name or "trend",
            ),
        ),
    )

    review = execute_promotion_review_request(
        conn,
        account_name="acct_service",
        strategy_name="Trend",
        requested_by="cam",
    )

    assert review.strategy_name == "trend"

    with pytest.raises(ValueError, match="An open promotion review already exists"):
        execute_promotion_review_request(
            conn,
            account_name="acct_service",
            strategy_name="trend",
            requested_by="cam",
        )
