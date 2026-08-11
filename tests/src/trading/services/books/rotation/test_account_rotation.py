from __future__ import annotations

import pytest

from tests.support.books import (
    assign_test_book_strategy,
    insert_test_book,
    set_test_book_rotation_scheduling,
)
from tests.support.promotion import make_ready_evaluation
from tests.support.repositories import insert_repository_account
from trading.models.evaluation import (
    EvaluationBacktestEvidence,
    EvaluationConfidence,
    StrategyEvaluationArtifact,
)
from trading.repositories.strategies import StrategyRepository
from trading.services.accounts import get_account
from trading.services.books.book_assignments import open_assignment_for_book
from trading.services.books.rotation.account_rotation import run_account_book_rotations
from trading.services.promotion import (
    actions as promotion_actions,
    execute_promotion_review_action,
    execute_promotion_review_request,
)
from trading.services.promotion.actions import PromotionAssessment

_FETCH_TARGET = "trading.services.evaluation.fetch_strategy_evaluation_for_account_row"

# A wide margin so the rotation policy's outperformance/score-superiority gates
# clear regardless of the (neutral-default) stability/drawdown/regime components.
_INCUMBENT_SCORE = 0.5
_CHALLENGER_SCORE = 1.5
_CHALLENGER_TRADE_COUNT = 25


def _artifact(*, blended_score: float, trade_count: int) -> StrategyEvaluationArtifact:
    return StrategyEvaluationArtifact(
        backtest=EvaluationBacktestEvidence(available=True, trade_count=trade_count),
        confidence=EvaluationConfidence(blended_score=blended_score, overall_confidence=0.3),
    )


def _set_up_book(conn, *, account_name: str, live_trading_enabled: bool) -> int:
    account_id = insert_repository_account(conn, name=account_name)
    if live_trading_enabled:
        conn.execute("UPDATE accounts SET live_trading_enabled = 1 WHERE id = ?", (account_id,))
        conn.commit()
    book_id = insert_test_book(conn, account_id=account_id, name="core")
    assign_test_book_strategy(conn, book_id=book_id, strategy_name="trend")
    set_test_book_rotation_scheduling(conn, book_id=book_id, enabled=1, schedule=["trend", "meanrev"])
    # Promotion review requests resolve strategy names to their canonical
    # strategy id (validate_strategy_name: "meanrev" -> "mean_reversion"), so
    # the catalog row backing a review must be keyed on the canonical id even
    # though the rotation schedule holds the operator-typed alias.
    for strategy_key, primitive in (("trend", "trend"), ("mean_reversion", "mean_reversion")):
        if StrategyRepository(conn).fetch_by_key(strategy_key=strategy_key) is None:
            StrategyRepository(conn).insert(
                strategy_key=strategy_key,
                primitive=primitive,
                params_json="{}",
                created_at="2026-01-01T00:00:00Z",
                updated_at="2026-01-01T00:00:00Z",
            )
    return book_id


def _approve_meanrev(conn, *, account_name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        promotion_actions,
        "fetch_promotion_snapshot",
        lambda _conn, *, account_name, strategy_name=None: (
            make_ready_evaluation(account_name=account_name, strategy_name=strategy_name or "meanrev"),
            PromotionAssessment(
                account_name=account_name,
                strategy_name=strategy_name or "meanrev",
                stage="promotion_review",
                status="ready_for_review",
                ready_for_live=True,
            ),
        ),
    )
    review = execute_promotion_review_request(
        conn, account_name=account_name, strategy_name="meanrev", requested_by="cam"
    )
    execute_promotion_review_action(conn, review_id=int(review.id), action="approve", actor_name="reviewer")


def _run_rotation(conn, *, account_name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        _FETCH_TARGET,
        lambda _conn, _account, *, strategy_name: _artifact(
            blended_score=_CHALLENGER_SCORE if strategy_name == "meanrev" else _INCUMBENT_SCORE,
            trade_count=_CHALLENGER_TRADE_COUNT,
        ),
    )
    account = get_account(conn, account_name)
    run_account_book_rotations(conn, account=account, decision_time="2026-07-26T12:00:00Z")


def test_live_account_holds_when_challenger_is_not_promotion_approved(conn, monkeypatch: pytest.MonkeyPatch) -> None:
    book_id = _set_up_book(conn, account_name="acct_live_gate", live_trading_enabled=True)

    _run_rotation(conn, account_name="acct_live_gate", monkeypatch=monkeypatch)

    assignment = open_assignment_for_book(conn, book_id=book_id)
    assert assignment is not None
    assert assignment.strategy_name == "trend"


def test_live_account_rotates_once_challenger_is_promotion_approved(conn, monkeypatch: pytest.MonkeyPatch) -> None:
    book_id = _set_up_book(conn, account_name="acct_live_approved", live_trading_enabled=True)
    _approve_meanrev(conn, account_name="acct_live_approved", monkeypatch=monkeypatch)

    _run_rotation(conn, account_name="acct_live_approved", monkeypatch=monkeypatch)

    assignment = open_assignment_for_book(conn, book_id=book_id)
    assert assignment is not None
    assert assignment.strategy_name == "meanrev"


def test_paper_account_rotates_without_promotion_approval(conn, monkeypatch: pytest.MonkeyPatch) -> None:
    book_id = _set_up_book(conn, account_name="acct_paper", live_trading_enabled=False)

    _run_rotation(conn, account_name="acct_paper", monkeypatch=monkeypatch)

    assignment = open_assignment_for_book(conn, book_id=book_id)
    assert assignment is not None
    assert assignment.strategy_name == "meanrev"
