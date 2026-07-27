from __future__ import annotations

import pytest

import trading.services.books.rotation.engine as rotation_service
from tests.support.books import assign_test_book_strategy, insert_test_book
from tests.support.repositories import insert_repository_account
from trading.models.rotation.rotation_strategy_metrics import RotationStrategyMetrics
from trading.repositories.book_assignments import BookAssignmentRepository
from trading.repositories.rotation_decisions import RotationDecisionRepository
from trading.repositories.strategies import StrategyRepository
from trading.services.books.rotation.engine import (
    RotationPolicyConfig,
    evaluate_and_apply_book_rotation,
)


def _insert_book(conn, *, account_id: int, name: str = "core") -> int:
    return insert_test_book(
        conn,
        account_id=account_id,
        name=name,
        created_at="2026-05-01T00:00:00Z",
        updated_at="2026-05-01T00:00:00Z",
    )


def _incumbent_metrics(*, strategy_name: str) -> RotationStrategyMetrics:
    return RotationStrategyMetrics(
        strategy_name=strategy_name,
        trade_count=12,
        risk_adjusted_return=0.9,
        stability=0.5,
        drawdown_penalty=0.2,
        regime_fit=0.0,
    )


def test_evaluate_and_apply_book_rotation_rotates_and_updates_assignment(conn) -> None:
    account_id = insert_repository_account(conn, name="acct_book_rotate")
    book_id = _insert_book(conn, account_id=account_id)
    assign_test_book_strategy(conn, book_id=book_id, strategy_name="trend")

    challenger = RotationStrategyMetrics(
        strategy_name="meanrev",
        trade_count=30,
        risk_adjusted_return=1.4,
        stability=0.62,
        drawdown_penalty=0.25,
        regime_fit=0.03,
    )
    result = evaluate_and_apply_book_rotation(
        conn,
        book_id=book_id,
        incumbent=_incumbent_metrics(strategy_name="trend"),
        challengers=[challenger],
        config=RotationPolicyConfig(
            rolling_window_days=30,
            min_trades_in_window=20,
            outperformance_threshold_bps=25.0,
            cooldown_days=7,
            config_version="cfg-rot-a",
        ),
        decision_time="2026-05-05T12:00:00Z",
    )

    assert result.rotated is True
    assert result.decision.rotation_action == "rotate"
    assert result.decision.selected_strategy == "meanrev"

    # The *book* assignment is updated on rotate —
    # book_strategy_history is the single effective-dated assignment history.
    book_assignment = BookAssignmentRepository(conn).fetch_open(book_id=book_id)
    assert book_assignment is not None
    strategy = StrategyRepository(conn).fetch_by_id(strategy_id=book_assignment.strategy_id)
    assert strategy is not None
    assert strategy.strategy_key == "meanrev"

    latest_decision = RotationDecisionRepository(conn).fetch_latest_for_book(book_id=book_id)
    assert latest_decision is not None
    assert latest_decision.rotation_action == "rotate"
    assert latest_decision.config_version == "cfg-rot-a"


def test_evaluate_and_apply_book_rotation_holds_when_cooldown_active(conn) -> None:
    account_id = insert_repository_account(conn, name="acct_book_cooldown")
    book_id = _insert_book(conn, account_id=account_id)
    assign_test_book_strategy(conn, book_id=book_id, strategy_name="trend")
    RotationDecisionRepository(conn).insert_for_book(
        book_id=book_id,
        decision_time="2026-05-04T18:00:00Z",
        incumbent_strategy="trend",
        challenger_strategy="meanrev",
        selected_strategy="meanrev",
        rotation_action="rotate",
        cooldown_active=0,
        score_components_json='{"demo":1}',
        gate_results_json='{"demo":true}',
        decision_reason="rotate_to_challenger",
        config_version="cfg-old",
        created_at="2026-05-04T18:00:00Z",
    )

    challenger = RotationStrategyMetrics(
        strategy_name="meanrev",
        trade_count=40,
        risk_adjusted_return=2.0,
        stability=0.70,
        drawdown_penalty=0.10,
        regime_fit=0.05,
    )
    result = evaluate_and_apply_book_rotation(
        conn,
        book_id=book_id,
        incumbent=_incumbent_metrics(strategy_name="trend"),
        challengers=[challenger],
        config=RotationPolicyConfig(cooldown_days=7),
        decision_time="2026-05-05T12:00:00Z",
    )

    assert result.rotated is False
    assert result.decision.rotation_action == "hold"
    assert result.decision.decision_reason == "cooldown_active"

    held = BookAssignmentRepository(conn).fetch_open(book_id=book_id)
    assert held is not None
    strategy = StrategyRepository(conn).fetch_by_id(strategy_id=held.strategy_id)
    assert strategy is not None
    assert strategy.strategy_key == "trend"


def test_rotation_rolls_back_decision_when_assignment_fails(conn, monkeypatch) -> None:
    account_id = insert_repository_account(conn, name="acct_book_rotate_rollback")
    book_id = _insert_book(conn, account_id=account_id)
    assign_test_book_strategy(conn, book_id=book_id, strategy_name="trend")
    challenger = RotationStrategyMetrics(
        strategy_name="meanrev",
        trade_count=30,
        risk_adjusted_return=1.4,
        stability=0.62,
        drawdown_penalty=0.25,
        regime_fit=0.03,
    )

    def fail_assignment(*args, **kwargs) -> None:
        raise RuntimeError("assignment failed")

    monkeypatch.setattr(rotation_service, "assign_book_strategy", fail_assignment)

    with pytest.raises(RuntimeError, match="assignment failed"):
        evaluate_and_apply_book_rotation(
            conn,
            book_id=book_id,
            incumbent=_incumbent_metrics(strategy_name="trend"),
            challengers=[challenger],
            config=RotationPolicyConfig(min_trades_in_window=20, outperformance_threshold_bps=25.0),
            decision_time="2026-05-05T12:00:00Z",
        )

    assert RotationDecisionRepository(conn).fetch_latest_for_book(book_id=book_id) is None
    assignment = BookAssignmentRepository(conn).fetch_open(book_id=book_id)
    assert assignment is not None
    strategy = StrategyRepository(conn).fetch_by_id(strategy_id=assignment.strategy_id)
    assert strategy is not None
    assert strategy.strategy_key == "trend"
