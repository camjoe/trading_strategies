from dataclasses import replace

import pytest

from tests.support.promotion import make_ready_evaluation
from trading.services.promotion import (
    actions as promotion_actions,
    execute_promotion_review_action,
    execute_promotion_review_request,
    fetch_promotion_review_history,
)


def _ready_assessment(*, account_name: str = "acct_service", strategy_name: str = "trend_v1"):
    return promotion_actions.PromotionAssessment(
        account_name=account_name,
        strategy_name=strategy_name,
        stage="promotion_review",
        status="ready_for_review",
        ready_for_live=True,
    )


def test_execute_promotion_review_request_persists_frozen_snapshot(
    conn,
    promotion_account: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        promotion_actions,
        "_fetch_promotion_snapshot",
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
        "_fetch_promotion_snapshot",
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
        "_fetch_promotion_snapshot",
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


@pytest.mark.parametrize(
    ("artifact", "assessment", "message"),
    [
        (
            replace(make_ready_evaluation(), basic=replace(make_ready_evaluation().basic, account_id=None)),
            _ready_assessment(),
            "requires an account id",
        ),
        (
            replace(make_ready_evaluation(), basic=replace(make_ready_evaluation().basic, requested_strategy=None)),
            _ready_assessment(),
            "requires a resolved strategy",
        ),
        (
            make_ready_evaluation(),
            replace(_ready_assessment(), live_trading_enabled=True),
            "only available before live trading is enabled",
        ),
    ],
)
def test_require_request_context_validates_missing_fields(
    artifact,
    assessment,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        promotion_actions._require_request_context(artifact, assessment)


def test_execute_promotion_review_action_raises_when_review_is_missing(conn) -> None:
    with pytest.raises(ValueError, match="Promotion review 999 not found"):
        execute_promotion_review_action(conn, review_id=999, action="approve")


def test_execute_promotion_review_request_raises_when_created_review_cannot_be_reloaded(
    conn,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        promotion_actions,
        "_fetch_promotion_snapshot",
        lambda _conn, *, account_name, strategy_name=None: (
            make_ready_evaluation(account_name=account_name, strategy_name=strategy_name or "trend_v1"),
            _ready_assessment(account_name=account_name, strategy_name=strategy_name or "trend_v1"),
        ),
    )
    from unittest.mock import Mock

    mock_repo = Mock()
    mock_repo.fetch_open.return_value = None
    mock_repo.insert_review.return_value = promotion_actions.PromotionReviewRecord(id=77)
    mock_repo.fetch_by_id.return_value = None
    monkeypatch.setattr(promotion_actions, "PromotionReviewRepository", lambda conn: mock_repo)
    monkeypatch.setattr(promotion_actions, "_require_strategy_id", lambda _conn, *, strategy_name: 1)
    monkeypatch.setattr(promotion_actions, "_record_review_event", lambda *_args, **_kwargs: None)

    with pytest.raises(ValueError, match="Promotion review 77 not found after request creation"):
        execute_promotion_review_request(conn, account_name="acct_service", strategy_name="trend_v1")


def test_execute_promotion_review_request_requires_strategy_id(
    conn,
    promotion_account: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        promotion_actions,
        "_fetch_promotion_snapshot",
        lambda _conn, *, account_name, strategy_name=None: (
            make_ready_evaluation(account_name=account_name, strategy_name="rsi"),
            _ready_assessment(account_name=account_name, strategy_name="rsi"),
        ),
    )

    with pytest.raises(ValueError, match="requires a strategy_id for 'rsi'"):
        execute_promotion_review_request(conn, account_name="acct_service", strategy_name="rsi")


def test_execute_promotion_review_action_adds_note_without_closing_review(
    conn,
    promotion_account: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        promotion_actions,
        "_fetch_promotion_snapshot",
        lambda _conn, *, account_name, strategy_name=None: (
            make_ready_evaluation(account_name=account_name, strategy_name=strategy_name or "trend_v1"),
            _ready_assessment(account_name=account_name, strategy_name=strategy_name or "trend_v1"),
        ),
    )
    review = execute_promotion_review_request(conn, account_name="acct_service", requested_by="cam")

    updated = execute_promotion_review_action(
        conn,
        review_id=int(review.id),
        action="note",
        actor_name=" reviewer ",
        note="  follow up needed  ",
    )

    entries = fetch_promotion_review_history(conn, account_name="acct_service")
    assert updated.review_state == "requested"
    assert updated.closed_at is None
    assert updated.operator_summary_note == "follow up needed"
    assert entries[0].events[-1].event_type == "note_added"
    assert entries[0].events[-1].actor_name == "reviewer"
    assert entries[0].events[-1].note == "follow up needed"


def test_execute_promotion_review_action_rejects_non_ready_review(
    conn,
    promotion_account: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        promotion_actions,
        "_fetch_promotion_snapshot",
        lambda _conn, *, account_name, strategy_name=None: (
            make_ready_evaluation(account_name=account_name, strategy_name=strategy_name or "trend_v1"),
            replace(
                _ready_assessment(account_name=account_name, strategy_name=strategy_name or "trend_v1"),
                ready_for_live=False,
            ),
        ),
    )
    review = execute_promotion_review_request(conn, account_name="acct_service", requested_by="cam")

    rejected = execute_promotion_review_action(conn, review_id=int(review.id), action="reject", actor_name="ops")

    assert rejected.review_state == "rejected"
    assert rejected.reviewed_by == "ops"
    assert rejected.closed_at is not None


def test_execute_promotion_review_action_blocks_approval_when_not_ready_for_live(
    conn,
    promotion_account: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        promotion_actions,
        "_fetch_promotion_snapshot",
        lambda _conn, *, account_name, strategy_name=None: (
            make_ready_evaluation(account_name=account_name, strategy_name=strategy_name or "trend_v1"),
            replace(
                _ready_assessment(account_name=account_name, strategy_name=strategy_name or "trend_v1"),
                ready_for_live=False,
            ),
        ),
    )
    review = execute_promotion_review_request(conn, account_name="acct_service", requested_by="cam")

    with pytest.raises(ValueError, match="Only ready-for-live promotion reviews can be approved"):
        execute_promotion_review_action(conn, review_id=int(review.id), action="approve")


def test_execute_promotion_review_action_raises_for_closed_review(
    conn,
    promotion_account: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        promotion_actions,
        "_fetch_promotion_snapshot",
        lambda _conn, *, account_name, strategy_name=None: (
            make_ready_evaluation(account_name=account_name, strategy_name=strategy_name or "trend_v1"),
            _ready_assessment(account_name=account_name, strategy_name=strategy_name or "trend_v1"),
        ),
    )
    review = execute_promotion_review_request(conn, account_name="acct_service", requested_by="cam")
    execute_promotion_review_action(conn, review_id=int(review.id), action="approve", actor_name="reviewer")

    with pytest.raises(ValueError, match="already closed with state 'approved'"):
        execute_promotion_review_action(conn, review_id=int(review.id), action="note", note="late note")


def test_execute_promotion_review_action_rolls_back_event_for_stale_open_review(
    conn,
    promotion_account: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        promotion_actions,
        "_fetch_promotion_snapshot",
        lambda _conn, *, account_name, strategy_name=None: (
            make_ready_evaluation(account_name=account_name, strategy_name=strategy_name or "trend_v1"),
            _ready_assessment(account_name=account_name, strategy_name=strategy_name or "trend_v1"),
        ),
    )
    review = execute_promotion_review_request(conn, account_name="acct_service", requested_by="cam")
    stale_review = promotion_actions._require_open_review(conn, review_id=int(review.id))
    execute_promotion_review_action(conn, review_id=int(review.id), action="approve", actor_name="reviewer")
    event_count = len(fetch_promotion_review_history(conn, account_name="acct_service")[0].events)
    monkeypatch.setattr(promotion_actions, "_require_open_review", lambda _conn, *, review_id: stale_review)

    with pytest.raises(ValueError, match=f"Promotion review {review.id} was already closed"):
        execute_promotion_review_action(conn, review_id=int(review.id), action="reject", actor_name="stale-reviewer")

    history = fetch_promotion_review_history(conn, account_name="acct_service")
    assert history[0].review.review_state == "approved"
    assert len(history[0].events) == event_count


def test_resolve_review_closure_rejects_unsupported_action() -> None:
    with pytest.raises(ValueError, match="Unsupported promotion review action 'archive'"):
        promotion_actions._resolve_review_closure("archive", ready_for_live=True)
