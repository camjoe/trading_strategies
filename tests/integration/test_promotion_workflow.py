"""Integration test for the human-gated promotion workflow.

Covers the core capability "promotion workflow" from ``docs/overview.md``:
a review is requested, a human approves it, and the approval becomes visible
to the eligibility read that rotation uses. The request and approval run
through the real services, repository, and database; only the readiness
assessment is stubbed ready, so the test pins the state machine and the
promotion-to-eligibility crossing rather than the assessment thresholds.
"""

from __future__ import annotations

import sqlite3

import pytest

from tests.support.promotion import make_ready_evaluation
from trading.models.promotion import PromotionAssessment
from trading.repositories.strategies import StrategyRepository
from trading.services.accounts.mutations import create_account
from trading.services.promotion import actions as promotion_actions
from trading.services.promotion.actions import execute_promotion_review_action, execute_promotion_review_request
from trading.services.promotion.eligibility import is_strategy_approved_for_live
from trading.services.promotion.history import fetch_promotion_review_history

STRATEGY = "trend_v1"


def _stub_ready_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    def _snapshot(_conn: sqlite3.Connection, *, account_name: str, strategy_name: str | None = None):
        resolved = strategy_name or STRATEGY
        artifact = make_ready_evaluation(account_name=account_name, strategy_name=resolved)
        assessment = PromotionAssessment(
            account_name=account_name,
            strategy_name=resolved,
            stage="promotion_review",
            status="ready_for_review",
            ready_for_live=True,
        )
        return artifact, assessment

    monkeypatch.setattr(promotion_actions, "fetch_promotion_snapshot", _snapshot)


def test_promotion_request_then_approve_makes_strategy_live_eligible(
    conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    create_account(conn, "acct_promo", STRATEGY, 1_000.0, "SPY")
    if StrategyRepository(conn).fetch_by_key(strategy_key="trend") is None:
        StrategyRepository(conn).insert(
            strategy_key="trend",
            primitive="trend",
            params_json="{}",
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
        )
    account_id = conn.execute("SELECT id FROM accounts WHERE name = 'acct_promo'").fetchone()[0]
    _stub_ready_snapshot(monkeypatch)

    # Before any review the strategy is not eligible for live trading.
    assert is_strategy_approved_for_live(conn, account_id=account_id, strategy_name="trend") is False

    review = execute_promotion_review_request(
        conn,
        account_name="acct_promo",
        strategy_name=STRATEGY,
        requested_by="cam",
        note="please review",
    )
    assert review.review_state == "requested"

    approved = execute_promotion_review_action(
        conn,
        review_id=int(review.id),
        action="approve",
        actor_name="reviewer",
        note="approved",
    )
    assert approved.review_state == "approved"
    assert approved.closed_at is not None

    # The approval crosses into the eligibility read rotation depends on.
    assert is_strategy_approved_for_live(conn, account_id=account_id, strategy_name="trend") is True

    entries = fetch_promotion_review_history(conn, account_name="acct_promo")
    assert len(entries) == 1
    event_types = [event.event_type for event in entries[0].events]
    assert event_types[0] == "requested"
    assert "approved" in event_types
