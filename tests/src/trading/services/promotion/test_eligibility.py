from __future__ import annotations

import pytest

from tests.support.promotion import make_ready_evaluation
from trading.services.accounts import get_account
from trading.services.promotion import (
    actions as promotion_actions,
    execute_promotion_review_action,
    execute_promotion_review_request,
    is_strategy_approved_for_live,
)
from trading.services.promotion.actions import PromotionAssessment


def _ready_assessment(*, account_name: str = "acct_service", strategy_name: str = "trend_v1") -> PromotionAssessment:
    return PromotionAssessment(
        account_name=account_name,
        strategy_name=strategy_name,
        stage="promotion_review",
        status="ready_for_review",
        ready_for_live=True,
    )


def _stub_snapshot_fetch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        promotion_actions,
        "fetch_promotion_snapshot",
        lambda _conn, *, account_name, strategy_name=None: (
            make_ready_evaluation(account_name=account_name, strategy_name=strategy_name or "trend_v1"),
            _ready_assessment(account_name=account_name, strategy_name=strategy_name or "trend_v1"),
        ),
    )


def _approved(conn, *, strategy_name: str) -> bool:
    account_id = get_account(conn, "acct_service").id
    return is_strategy_approved_for_live(conn, account_id=account_id, strategy_name=strategy_name)


def test_no_review_is_not_approved(conn, promotion_account: None) -> None:
    assert _approved(conn, strategy_name="trend") is False


def test_requested_but_not_yet_reviewed_is_not_approved(
    conn, promotion_account: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_snapshot_fetch(monkeypatch)
    review = execute_promotion_review_request(conn, account_name="acct_service", requested_by="cam")

    assert _approved(conn, strategy_name=review.strategy_name) is False


def test_approved_review_is_approved(conn, promotion_account: None, monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_snapshot_fetch(monkeypatch)
    review = execute_promotion_review_request(conn, account_name="acct_service", requested_by="cam")
    execute_promotion_review_action(conn, review_id=int(review.id), action="approve", actor_name="reviewer")

    assert _approved(conn, strategy_name=review.strategy_name) is True


def test_rejected_review_is_not_approved(conn, promotion_account: None, monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_snapshot_fetch(monkeypatch)
    review = execute_promotion_review_request(conn, account_name="acct_service", requested_by="cam")
    execute_promotion_review_action(conn, review_id=int(review.id), action="reject", actor_name="reviewer")

    assert _approved(conn, strategy_name=review.strategy_name) is False


def test_later_request_supersedes_an_earlier_approval(
    conn, promotion_account: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_snapshot_fetch(monkeypatch)
    first_review = execute_promotion_review_request(conn, account_name="acct_service", requested_by="cam")
    execute_promotion_review_action(conn, review_id=int(first_review.id), action="approve", actor_name="reviewer")

    execute_promotion_review_request(conn, account_name="acct_service", requested_by="cam")

    assert _approved(conn, strategy_name=first_review.strategy_name) is False


def test_approved_review_matches_when_checked_by_an_alias(
    conn, promotion_account: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The review persists under the canonical strategy id ("trend"), but a
    # caller (e.g. a book's rotation schedule) may hold the operator-typed
    # alias ("trend_v1") instead — the check must canonicalize to match.
    _stub_snapshot_fetch(monkeypatch)
    review = execute_promotion_review_request(conn, account_name="acct_service", requested_by="cam")
    execute_promotion_review_action(conn, review_id=int(review.id), action="approve", actor_name="reviewer")
    assert review.strategy_name != "trend_v1"

    assert _approved(conn, strategy_name="trend_v1") is True


def test_unresolvable_strategy_name_is_not_approved(conn, promotion_account: None) -> None:
    assert _approved(conn, strategy_name="not_a_real_strategy") is False
