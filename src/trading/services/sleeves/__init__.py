"""Sleeve services package.

This package is the stable public sleeve-orchestration surface for sleeve-level
accounting updates and account-vs-sleeve reconciliation.
"""

from __future__ import annotations

from trading.models.sleeves.sleeve_risk_decision import SleeveRiskDecision
from trading.models.sleeves.sleeve_risk_gate_config import SleeveRiskGateConfig
from trading.models.sleeves.sleeve_risk_gate_result import SleeveRiskGateResult
from trading.models.sleeves.sleeve_trade_intent import SleeveTradeIntent
from trading.services.sleeves.accounting import SleeveFillApplicationResult, apply_sleeve_fill
from trading.services.sleeves.execution import (
    generate_sleeve_trade_intents,
    run_sleeve_mode_for_account,
)
from trading.services.sleeves.reconciliation import (
    SleeveEquityReconciliationResult,
    reconcile_sleeves_vs_account_equity,
    reconcile_sleeves_vs_latest_snapshot,
)
from trading.services.sleeves.risk_gate import evaluate_sleeve_risk_gate
from trading.services.sleeves.rotation import (
    SleeveRotationConfig,
    SleeveRotationRunResult,
    evaluate_and_apply_sleeve_rotation,
)
from trading.services.sleeves.shadow_evaluation import (
    DEFAULT_SHADOW_ROLLING_WINDOW_DAYS,
    ShadowEvaluationRun,
    SleeveShadowEvaluation,
    build_challenger_metrics_from_backtest_returns,
    build_sleeve_shadow_evaluation,
)

__all__ = [
    "SleeveFillApplicationResult",
    "SleeveTradeIntent",
    "SleeveEquityReconciliationResult",
    "apply_sleeve_fill",
    "generate_sleeve_trade_intents",
    "reconcile_sleeves_vs_account_equity",
    "reconcile_sleeves_vs_latest_snapshot",
    "run_sleeve_mode_for_account",
    "SleeveRiskDecision",
    "SleeveRiskGateConfig",
    "SleeveRiskGateResult",
    "evaluate_sleeve_risk_gate",
    "SleeveRotationConfig",
    "SleeveRotationRunResult",
    "evaluate_and_apply_sleeve_rotation",
    "DEFAULT_SHADOW_ROLLING_WINDOW_DAYS",
    "ShadowEvaluationRun",
    "SleeveShadowEvaluation",
    "build_challenger_metrics_from_backtest_returns",
    "build_sleeve_shadow_evaluation",
]
