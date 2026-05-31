from __future__ import annotations

from trading.domain.sleeve_rotation import SleeveStrategyMetrics
from trading.repositories.daily_metrics import DailyMetricsRepository
from trading.repositories.rotation_decisions import (
    fetch_latest_rotation_decision_for_sleeve,
    insert_rotation_decision,
)
from trading.repositories.sleeves import (
    fetch_active_sleeve_strategy_assignment,
    fetch_sleeve_strategy_assignments,
    insert_sleeve_strategy_assignment,
)
from trading.services.sleeves.rotation import (
    SleeveRotationConfig,
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


def _seed_incumbent_metrics(conn, *, account_id: int, sleeve_id: int) -> None:
    DailyMetricsRepository(conn).upsert(
        account_id=account_id,
        sleeve_id=sleeve_id,
        metric_date="2026-05-03",
        return_pct=0.8,
        drawdown_pct=-0.6,
        turnover_pct=3.0,
        slippage_bps=8.0,
        hit_rate=0.50,
        expectancy=0.10,
        risk_adjusted_score=0.9,
        trade_count=12,
        fees_total=2.5,
        created_at="2026-05-03T23:59:00Z",
        updated_at="2026-05-03T23:59:00Z",
    )
    DailyMetricsRepository(conn).upsert(
        account_id=account_id,
        sleeve_id=sleeve_id,
        metric_date="2026-05-04",
        return_pct=0.7,
        drawdown_pct=-0.5,
        turnover_pct=2.8,
        slippage_bps=7.0,
        hit_rate=0.48,
        expectancy=0.09,
        risk_adjusted_score=0.85,
        trade_count=11,
        fees_total=2.1,
        created_at="2026-05-04T23:59:00Z",
        updated_at="2026-05-04T23:59:00Z",
    )


def test_evaluate_and_apply_sleeve_rotation_rotates_and_updates_assignment(conn) -> None:
    account_id = insert_repository_account(conn, name="acct_sleeve_rotate")
    sleeve_id = _insert_sleeve(conn, account_id=account_id)
    insert_sleeve_strategy_assignment(
        conn,
        sleeve_id=sleeve_id,
        strategy_name="trend",
        param_set_id=101,
        effective_from="2026-05-01T00:00:00Z",
        effective_to=None,
        is_incumbent=1,
        created_at="2026-05-01T00:00:00Z",
        updated_at="2026-05-01T00:00:00Z",
    )
    _seed_incumbent_metrics(conn, account_id=account_id, sleeve_id=sleeve_id)

    challenger = SleeveStrategyMetrics(
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
        challengers=[challenger],
        config=SleeveRotationConfig(
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

    active_assignment = fetch_active_sleeve_strategy_assignment(conn, sleeve_id=sleeve_id)
    assert active_assignment is not None
    assert active_assignment["strategy_name"] == "meanrev"
    assert int(active_assignment["param_set_id"]) == 202

    assignments = fetch_sleeve_strategy_assignments(conn, sleeve_id=sleeve_id)
    assert len(assignments) == 2

    latest_decision = fetch_latest_rotation_decision_for_sleeve(conn, sleeve_id=sleeve_id)
    assert latest_decision is not None
    assert latest_decision["rotation_action"] == "rotate"
    assert latest_decision["config_version"] == "cfg-rot-a"


def test_evaluate_and_apply_sleeve_rotation_holds_when_cooldown_active(conn) -> None:
    account_id = insert_repository_account(conn, name="acct_sleeve_cooldown")
    sleeve_id = _insert_sleeve(conn, account_id=account_id)
    insert_sleeve_strategy_assignment(
        conn,
        sleeve_id=sleeve_id,
        strategy_name="trend",
        param_set_id=111,
        effective_from="2026-05-01T00:00:00Z",
        effective_to=None,
        is_incumbent=1,
        created_at="2026-05-01T00:00:00Z",
        updated_at="2026-05-01T00:00:00Z",
    )
    _seed_incumbent_metrics(conn, account_id=account_id, sleeve_id=sleeve_id)
    insert_rotation_decision(
        conn,
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

    challenger = SleeveStrategyMetrics(
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
        challengers=[challenger],
        config=SleeveRotationConfig(cooldown_days=7),
        decision_time="2026-05-05T12:00:00Z",
    )

    assert result.rotated is False
    assert result.decision.rotation_action == "hold"
    assert result.decision.decision_reason == "cooldown_active"

    active_assignment = fetch_active_sleeve_strategy_assignment(conn, sleeve_id=sleeve_id)
    assert active_assignment is not None
    assert active_assignment["strategy_name"] == "trend"
