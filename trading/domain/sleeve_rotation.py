from __future__ import annotations

from dataclasses import dataclass

# Conversion factor from percentage points to basis points.
PERCENT_TO_BASIS_POINTS = 100.0


@dataclass(frozen=True, slots=True)
class SleeveRotationScoreWeights:
    risk_adjusted_return_weight: float = 1.0
    stability_weight: float = 0.25
    drawdown_penalty_weight: float = 0.20
    cost_penalty_weight: float = 0.10
    regime_fit_weight: float = 0.10


@dataclass(frozen=True, slots=True)
class SleeveStrategyMetrics:
    strategy_name: str
    param_set_id: int | None
    trade_count: int
    risk_adjusted_return: float
    stability: float
    drawdown_penalty: float
    cost_penalty: float
    regime_fit: float


@dataclass(frozen=True, slots=True)
class SleeveStrategyScore:
    strategy_name: str
    param_set_id: int | None
    score: float
    score_components: dict[str, float]
    trade_count: int
    risk_adjusted_return: float


@dataclass(frozen=True, slots=True)
class SleeveRotationDecision:
    rotation_action: str
    selected_strategy: str
    selected_param_set_id: int | None
    incumbent_strategy: str
    challenger_strategy: str | None
    challenger_param_set_id: int | None
    cooldown_active: bool
    decision_reason: str
    score_components: dict[str, dict[str, float]]
    gate_results: dict[str, object]


def _compute_score(
    metrics: SleeveStrategyMetrics,
    *,
    weights: SleeveRotationScoreWeights,
) -> SleeveStrategyScore:
    weighted_risk_adjusted_return = weights.risk_adjusted_return_weight * float(metrics.risk_adjusted_return)
    weighted_stability = weights.stability_weight * float(metrics.stability)
    weighted_drawdown_penalty = weights.drawdown_penalty_weight * float(metrics.drawdown_penalty)
    weighted_cost_penalty = weights.cost_penalty_weight * float(metrics.cost_penalty)
    weighted_regime_fit = weights.regime_fit_weight * float(metrics.regime_fit)

    score = (
        weighted_risk_adjusted_return
        + weighted_stability
        - weighted_drawdown_penalty
        - weighted_cost_penalty
        + weighted_regime_fit
    )
    return SleeveStrategyScore(
        strategy_name=metrics.strategy_name,
        param_set_id=metrics.param_set_id,
        score=score,
        score_components={
            "risk_adjusted_return": weighted_risk_adjusted_return,
            "stability": weighted_stability,
            "drawdown_penalty": weighted_drawdown_penalty,
            "cost_penalty": weighted_cost_penalty,
            "regime_fit": weighted_regime_fit,
            "total_score": score,
        },
        trade_count=int(metrics.trade_count),
        risk_adjusted_return=float(metrics.risk_adjusted_return),
    )


def evaluate_champion_challenger_rotation(
    *,
    incumbent: SleeveStrategyMetrics,
    challengers: list[SleeveStrategyMetrics],
    min_trades_in_window: int,
    outperformance_threshold_bps: float,
    cooldown_active: bool,
    weights: SleeveRotationScoreWeights = SleeveRotationScoreWeights(),
) -> SleeveRotationDecision:
    incumbent_score = _compute_score(incumbent, weights=weights)
    challenger_scores = [_compute_score(item, weights=weights) for item in challengers]
    best_challenger = max(challenger_scores, key=lambda item: item.score) if challenger_scores else None

    score_components: dict[str, dict[str, float]] = {
        incumbent_score.strategy_name: incumbent_score.score_components,
    }
    if best_challenger is not None:
        score_components[best_challenger.strategy_name] = best_challenger.score_components

    if best_challenger is None:
        return SleeveRotationDecision(
            rotation_action="hold",
            selected_strategy=incumbent_score.strategy_name,
            selected_param_set_id=incumbent_score.param_set_id,
            incumbent_strategy=incumbent_score.strategy_name,
            challenger_strategy=None,
            challenger_param_set_id=None,
            cooldown_active=bool(cooldown_active),
            decision_reason="no_challenger_candidates",
            score_components=score_components,
            gate_results={
                "cooldown_gate_passed": not bool(cooldown_active),
                "sample_size_gate_passed": False,
                "outperformance_gate_passed": False,
                "score_superiority_gate_passed": False,
                "outperformance_bps": None,
                "min_trades_in_window": int(min_trades_in_window),
                "outperformance_threshold_bps": float(outperformance_threshold_bps),
            },
        )

    outperformance_bps = (
        best_challenger.risk_adjusted_return - incumbent_score.risk_adjusted_return
    ) * PERCENT_TO_BASIS_POINTS
    sample_size_gate_passed = best_challenger.trade_count >= int(min_trades_in_window)
    outperformance_gate_passed = outperformance_bps >= float(outperformance_threshold_bps)
    score_superiority_gate_passed = best_challenger.score > incumbent_score.score
    cooldown_gate_passed = not bool(cooldown_active)
    should_rotate = (
        cooldown_gate_passed
        and sample_size_gate_passed
        and outperformance_gate_passed
        and score_superiority_gate_passed
    )

    if should_rotate:
        decision_reason = "rotate_to_challenger"
    elif not cooldown_gate_passed:
        decision_reason = "cooldown_active"
    elif not sample_size_gate_passed:
        decision_reason = "challenger_min_sample_not_met"
    elif not outperformance_gate_passed:
        decision_reason = "challenger_outperformance_below_threshold"
    else:
        decision_reason = "challenger_score_not_superior"

    return SleeveRotationDecision(
        rotation_action="rotate" if should_rotate else "hold",
        selected_strategy=(best_challenger.strategy_name if should_rotate else incumbent_score.strategy_name),
        selected_param_set_id=(best_challenger.param_set_id if should_rotate else incumbent_score.param_set_id),
        incumbent_strategy=incumbent_score.strategy_name,
        challenger_strategy=best_challenger.strategy_name,
        challenger_param_set_id=best_challenger.param_set_id,
        cooldown_active=bool(cooldown_active),
        decision_reason=decision_reason,
        score_components=score_components,
        gate_results={
            "cooldown_gate_passed": cooldown_gate_passed,
            "sample_size_gate_passed": sample_size_gate_passed,
            "outperformance_gate_passed": outperformance_gate_passed,
            "score_superiority_gate_passed": score_superiority_gate_passed,
            "outperformance_bps": outperformance_bps,
            "min_trades_in_window": int(min_trades_in_window),
            "outperformance_threshold_bps": float(outperformance_threshold_bps),
            "incumbent_score": incumbent_score.score,
            "challenger_score": best_challenger.score,
        },
    )
