from __future__ import annotations

from trading.domain.rotation.policy import evaluate_champion_challenger_rotation
from trading.models.rotation.rotation_strategy_metrics import RotationStrategyMetrics


def _incumbent() -> RotationStrategyMetrics:
    return RotationStrategyMetrics(
        strategy_name="trend",
        trade_count=30,
        risk_adjusted_return=1.0,
        stability=0.52,
        drawdown_penalty=0.30,
        cost_penalty=0.05,
        regime_fit=0.0,
    )


def test_evaluate_champion_challenger_rotation_rotates_when_all_gates_pass() -> None:
    challenger = RotationStrategyMetrics(
        strategy_name="meanrev",
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
    assert decision.decision_reason == "rotate_to_challenger"
    assert decision.gate_results["cooldown_gate_passed"] is True
    assert decision.gate_results["sample_size_gate_passed"] is True
    assert decision.gate_results["outperformance_gate_passed"] is True
    assert decision.gate_results["score_superiority_gate_passed"] is True


def test_evaluate_champion_challenger_rotation_holds_on_cooldown() -> None:
    challenger = RotationStrategyMetrics(
        strategy_name="meanrev",
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
    challenger = RotationStrategyMetrics(
        strategy_name="meanrev",
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
    challenger = RotationStrategyMetrics(
        strategy_name="meanrev",
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


def _equal_return_pair(
    *,
    incumbent_stability: float = 0.0,
    incumbent_drawdown: float = 0.0,
    challenger_stability: float = 0.0,
    challenger_drawdown: float = 0.0,
) -> tuple[RotationStrategyMetrics, RotationStrategyMetrics]:
    """Two strategies with identical returns, differing only in a risk component."""

    def _metrics(name: str, stability: float, drawdown_penalty: float) -> RotationStrategyMetrics:
        return RotationStrategyMetrics(
            strategy_name=name,
            trade_count=50,
            risk_adjusted_return=5.0,
            stability=stability,
            drawdown_penalty=drawdown_penalty,
            cost_penalty=0.0,
            regime_fit=0.0,
        )

    return (
        _metrics("incumbent", incumbent_stability, incumbent_drawdown),
        _metrics("challenger", challenger_stability, challenger_drawdown),
    )


def test_deeper_drawdown_challenger_does_not_win_on_equal_returns() -> None:
    # The whole point of the drawdown component: identical returns must not be
    # treated as identical quality when one strategy got there far more painfully.
    incumbent, challenger = _equal_return_pair(incumbent_drawdown=4.0, challenger_drawdown=25.0)

    decision = evaluate_champion_challenger_rotation(
        incumbent=incumbent,
        challengers=[challenger],
        min_trades_in_window=10,
        outperformance_threshold_bps=0.0,
        cooldown_active=False,
    )

    assert decision.rotation_action == "hold"
    assert decision.decision_reason == "challenger_score_not_superior"
    assert (
        decision.score_components["challenger"]["total_score"] < decision.score_components["incumbent"]["total_score"]
    )


def test_less_consistent_challenger_does_not_win_on_equal_returns() -> None:
    incumbent, challenger = _equal_return_pair(incumbent_stability=-1.0, challenger_stability=-20.0)

    decision = evaluate_champion_challenger_rotation(
        incumbent=incumbent,
        challengers=[challenger],
        min_trades_in_window=10,
        outperformance_threshold_bps=0.0,
        cooldown_active=False,
    )

    assert decision.rotation_action == "hold"
    assert decision.decision_reason == "challenger_score_not_superior"


def test_steadier_shallower_challenger_still_wins_when_returns_lead() -> None:
    # Risk components must discriminate without blocking a genuinely better challenger.
    incumbent = RotationStrategyMetrics(
        strategy_name="incumbent",
        trade_count=50,
        risk_adjusted_return=5.0,
        stability=-10.0,
        drawdown_penalty=20.0,
        cost_penalty=0.0,
        regime_fit=0.0,
    )
    challenger = RotationStrategyMetrics(
        strategy_name="challenger",
        trade_count=50,
        risk_adjusted_return=6.0,
        stability=-2.0,
        drawdown_penalty=5.0,
        cost_penalty=0.0,
        regime_fit=0.0,
    )

    decision = evaluate_champion_challenger_rotation(
        incumbent=incumbent,
        challengers=[challenger],
        min_trades_in_window=10,
        outperformance_threshold_bps=25.0,
        cooldown_active=False,
    )

    assert decision.rotation_action == "rotate"
    assert decision.selected_strategy == "challenger"
