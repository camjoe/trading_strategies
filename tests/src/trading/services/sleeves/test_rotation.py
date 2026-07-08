from __future__ import annotations

from trading.models.rotation.rotation_strategy_metrics import RotationStrategyMetrics
from trading.repositories.rotation_decisions import RotationDecisionRepository
from trading.repositories.sleeves import SleeveRepository
from trading.services.sleeves.rotation import (
    RotationPolicyConfig,
    evaluate_and_apply_sleeve_rotation,
)
from tests.support.repositories import insert_repository_account
from tests.support.sleeves import insert_test_sleeve


def _insert_sleeve(conn, *, account_id: int, name: str = "core") -> int:
    return insert_test_sleeve(
        conn,
        account_id=account_id,
        name=name,
        created_at="2026-05-01T00:00:00Z",
        updated_at="2026-05-01T00:00:00Z",
    )


def _incumbent_metrics(*, strategy_name: str, param_set_id: int | None) -> RotationStrategyMetrics:
    return RotationStrategyMetrics(
        strategy_name=strategy_name,
        param_set_id=param_set_id,
        trade_count=12,
        risk_adjusted_return=0.9,
        stability=0.5,
        drawdown_penalty=0.2,
        cost_penalty=0.05,
        regime_fit=0.0,
    )


def _insert_param_set(conn, param_set_id: int, strategy_name: str) -> None:
    conn.execute(
        """
        INSERT INTO strategy_param_sets (id, strategy_name, version, params_json, created_at, updated_at)
        VALUES (?, ?, 'v1', '{}', '2026-05-01T00:00:00Z', '2026-05-01T00:00:00Z')
        """,
        (param_set_id, strategy_name),
    )


def test_evaluate_and_apply_sleeve_rotation_rotates_and_updates_assignment(conn) -> None:
    account_id = insert_repository_account(conn, name="acct_sleeve_rotate")
    sleeve_id = _insert_sleeve(conn, account_id=account_id)
    _insert_param_set(conn, 101, "trend")
    _insert_param_set(conn, 202, "meanrev")
    SleeveRepository(conn).insert_assignment(
        sleeve_id=sleeve_id,
        strategy_name="trend",
        param_set_id=101,
        effective_from="2026-05-01T00:00:00Z",
        effective_to=None,
        is_incumbent=1,
        created_at="2026-05-01T00:00:00Z",
        updated_at="2026-05-01T00:00:00Z",
    )

    challenger = RotationStrategyMetrics(
        strategy_name="meanrev",
        param_set_id=202,
        trade_count=30,
        risk_adjusted_return=1.4,
        stability=0.62,
        drawdown_penalty=0.25,
        cost_penalty=0.04,
        regime_fit=0.03,
    )
    result = evaluate_and_apply_sleeve_rotation(
        conn,
        sleeve_id=sleeve_id,
        incumbent=_incumbent_metrics(strategy_name="trend", param_set_id=101),
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

    sleeve_repo = SleeveRepository(conn)
    active_assignment = sleeve_repo.fetch_active_assignment(sleeve_id=sleeve_id)
    assert active_assignment is not None
    assert active_assignment.strategy_name == "meanrev"
    assert active_assignment.param_set_id == 202

    assignments = sleeve_repo.fetch_assignments(sleeve_id=sleeve_id)
    assert len(assignments) == 2

    latest_decision = RotationDecisionRepository(conn).fetch_latest(sleeve_id=sleeve_id)
    assert latest_decision is not None
    assert latest_decision["rotation_action"] == "rotate"
    assert latest_decision["config_version"] == "cfg-rot-a"


def test_evaluate_and_apply_sleeve_rotation_holds_when_cooldown_active(conn) -> None:
    account_id = insert_repository_account(conn, name="acct_sleeve_cooldown")
    sleeve_id = _insert_sleeve(conn, account_id=account_id)
    _insert_param_set(conn, 111, "trend")
    _insert_param_set(conn, 222, "meanrev")
    SleeveRepository(conn).insert_assignment(
        sleeve_id=sleeve_id,
        strategy_name="trend",
        param_set_id=111,
        effective_from="2026-05-01T00:00:00Z",
        effective_to=None,
        is_incumbent=1,
        created_at="2026-05-01T00:00:00Z",
        updated_at="2026-05-01T00:00:00Z",
    )
    RotationDecisionRepository(conn).insert(
        sleeve_id=sleeve_id,
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
        param_set_id=222,
        created_at="2026-05-04T18:00:00Z",
    )

    challenger = RotationStrategyMetrics(
        strategy_name="meanrev",
        param_set_id=222,
        trade_count=40,
        risk_adjusted_return=2.0,
        stability=0.70,
        drawdown_penalty=0.10,
        cost_penalty=0.01,
        regime_fit=0.05,
    )
    result = evaluate_and_apply_sleeve_rotation(
        conn,
        sleeve_id=sleeve_id,
        incumbent=_incumbent_metrics(strategy_name="trend", param_set_id=111),
        challengers=[challenger],
        config=RotationPolicyConfig(cooldown_days=7),
        decision_time="2026-05-05T12:00:00Z",
    )

    assert result.rotated is False
    assert result.decision.rotation_action == "hold"
    assert result.decision.decision_reason == "cooldown_active"

    active_assignment = SleeveRepository(conn).fetch_active_assignment(sleeve_id=sleeve_id)
    assert active_assignment is not None
    assert active_assignment.strategy_name == "trend"
