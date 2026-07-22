"""Multi-book trading services package.

The stable public surface for multi-book trade orchestration: book assignments,
rotation, and challenger shadow evaluation. (Book-keyed intent generation now
lives in ``trading.services.execution.selection``.)
"""

from __future__ import annotations

from trading.models.execution.risk_gate_decision import RiskGateDecision
from trading.models.execution.risk_gate_config import RiskGateConfig
from trading.models.execution.risk_gate_result import RiskGateResult
from trading.models.execution.book_trade_candidate import BookTradeCandidate
from trading.services.books.rotation import (
    RotationPolicyConfig,
    RotationRunResult,
    evaluate_and_apply_book_rotation,
)
from trading.services.books.rotation_metrics import build_rotation_strategy_metrics
from trading.services.books.challenger_evaluation import (
    ChallengerEvaluationRun,
    BookChallengerEvaluation,
    build_book_challenger_evaluations,
)

__all__ = [
    "BookTradeCandidate",
    "RiskGateDecision",
    "RiskGateConfig",
    "RiskGateResult",
    "RotationPolicyConfig",
    "RotationRunResult",
    "evaluate_and_apply_book_rotation",
    "build_rotation_strategy_metrics",
    "ChallengerEvaluationRun",
    "BookChallengerEvaluation",
    "build_book_challenger_evaluations",
]
