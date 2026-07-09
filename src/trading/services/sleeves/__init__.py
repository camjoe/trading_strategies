"""Multi-book trading services package (legacy name: sleeves; renamed in SR-6).

The stable public surface for multi-book trade orchestration: book assignments,
intent generation, rotation, and challenger shadow evaluation.
"""

from __future__ import annotations

from trading.models.sleeves.sleeve_risk_decision import SleeveRiskDecision
from trading.models.sleeves.sleeve_risk_gate_config import SleeveRiskGateConfig
from trading.models.sleeves.sleeve_risk_gate_result import SleeveRiskGateResult
from trading.models.sleeves.sleeve_trade_intent import SleeveTradeIntent
from trading.services.sleeves.execution import (
    generate_sleeve_trade_intents,
    run_sleeve_mode_for_account,
)
from trading.services.sleeves.rotation import (
    RotationPolicyConfig,
    RotationRunResult,
    evaluate_and_apply_sleeve_rotation,
)
from trading.services.sleeves.rotation_metrics import build_rotation_strategy_metrics
from trading.services.sleeves.shadow_evaluation import (
    DEFAULT_SHADOW_ROLLING_WINDOW_DAYS,
    ShadowEvaluationRun,
    SleeveShadowEvaluation,
    build_sleeve_shadow_evaluation,
)

__all__ = [
    "SleeveTradeIntent",
    "generate_sleeve_trade_intents",
    "run_sleeve_mode_for_account",
    "SleeveRiskDecision",
    "SleeveRiskGateConfig",
    "SleeveRiskGateResult",
    "RotationPolicyConfig",
    "RotationRunResult",
    "evaluate_and_apply_sleeve_rotation",
    "build_rotation_strategy_metrics",
    "DEFAULT_SHADOW_ROLLING_WINDOW_DAYS",
    "ShadowEvaluationRun",
    "SleeveShadowEvaluation",
    "build_sleeve_shadow_evaluation",
]
