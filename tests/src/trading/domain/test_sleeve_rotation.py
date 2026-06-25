from __future__ import annotations

from trading.domain.sleeve_rotation import evaluate_champion_challenger_rotation
from trading.models.sleeves.sleeve_strategy_metrics import SleeveStrategyMetrics


def _incumbent() -> SleeveStrategyMetrics:
    return SleeveStrategyMetrics(
        strategy_name="trend",
        param_set_id=11,
        trade_count=30,
        risk_adjusted_return=1.0,
        stability=0.52,
        drawdown_penalty=0.30,
        cost_penalty=0.05,
        regime_fit=0.0,
    )


def test_evaluate_champion_challenger_rotation_rotates_when_all_gates_pass() -> None:
    challenger = SleeveStrategyMetrics(
        strategy_name="meanrev",
        param_set_id=22,
        trade_count=40,
        risk_adjusted_return=1.5,
        stability=0.60,
        drawdown_penalty=0.20,
        cost_penalty=0.03,
        regime_fit=0.05,
    )

    decision = evaluate_champion_challenger_rotation(
        incumbent=_incumbent(),
        challengers=[challenger],
        min_trades_in_window=20,
        outperformance_threshold_bps=25.0,
        cooldown_active=False,
    )

    assert decision.rotation_action == "rotate"
    assert decision.selected_strategy == "meanrev"
    assert decision.selected_param_set_id == 22
    assert decision.decision_reason == "rotate_to_challenger"
    assert decision.gate_results["cooldown_gate_passed"] is True
    assert decision.gate_results["sample_size_gate_passed"] is True
    assert decision.gate_results["outperformance_gate_passed"] is True
    assert decision.gate_results["score_superiority_gate_passed"] is True


def test_evaluate_champion_challenger_rotation_holds_on_cooldown() -> None:
    challenger = SleeveStrategyMetrics(
        strategy_name="meanrev",
        param_set_id=22,
        trade_count=40,
        risk_adjusted_return=1.8,
        stability=0.70,
        drawdown_penalty=0.20,
        cost_penalty=0.02,
        regime_fit=0.06,
    )

    decision = evaluate_champion_challenger_rotation(
        incumbent=_incumbent(),
        challengers=[challenger],
        min_trades_in_window=20,
        outperformance_threshold_bps=25.0,
        cooldown_active=True,
    )

    assert decision.rotation_action == "hold"
    assert decision.selected_strategy == "trend"
    assert decision.decision_reason == "cooldown_active"
    assert decision.gate_results["cooldown_gate_passed"] is False


def test_evaluate_champion_challenger_rotation_holds_when_threshold_not_met() -> None:
    challenger = SleeveStrategyMetrics(
        strategy_name="meanrev",
        param_set_id=22,
        trade_count=30,
        risk_adjusted_return=1.05,
        stability=0.60,
        drawdown_penalty=0.30,
        cost_penalty=0.05,
        regime_fit=0.0,
    )

    decision = evaluate_champion_challenger_rotation(
        incumbent=_incumbent(),
        challengers=[challenger],
        min_trades_in_window=20,
        outperformance_threshold_bps=25.0,
        cooldown_active=False,
    )

    assert decision.rotation_action == "hold"
    assert decision.selected_strategy == "trend"
    assert decision.decision_reason == "challenger_outperformance_below_threshold"
    assert decision.gate_results["outperformance_gate_passed"] is False


def test_evaluate_champion_challenger_rotation_holds_when_sample_size_not_met() -> None:
    challenger = SleeveStrategyMetrics(
        strategy_name="meanrev",
        param_set_id=22,
        trade_count=5,
        risk_adjusted_return=2.0,
        stability=0.65,
        drawdown_penalty=0.15,
        cost_penalty=0.01,
        regime_fit=0.05,
    )

    decision = evaluate_champion_challenger_rotation(
        incumbent=_incumbent(),
        challengers=[challenger],
        min_trades_in_window=20,
        outperformance_threshold_bps=25.0,
        cooldown_active=False,
    )

    assert decision.rotation_action == "hold"
    assert decision.selected_strategy == "trend"
    assert decision.decision_reason == "challenger_min_sample_not_met"
    assert decision.gate_results["sample_size_gate_passed"] is False
