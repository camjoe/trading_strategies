"""Evaluation artifact data contracts.

Stable re-export surface for the strategy-evaluation artifact and its parts.
"""

from __future__ import annotations

from trading.models.evaluation.backtest_freshness import BacktestFreshness
from trading.models.evaluation.constants import EVALUATION_ARTIFACT_VERSION, EVALUATION_SOURCE_MODE
from trading.models.evaluation.evaluation_backtest_evidence import EvaluationBacktestEvidence
from trading.models.evaluation.evaluation_basic_scope import EvaluationBasicScope
from trading.models.evaluation.evaluation_confidence import EvaluationConfidence
from trading.models.evaluation.evaluation_decision_score import EvaluationDecisionScore
from trading.models.evaluation.evaluation_diagnostics import EvaluationDiagnostics
from trading.models.evaluation.evaluation_meta import EvaluationMeta
from trading.models.evaluation.evaluation_paper_live_evidence import EvaluationPaperLiveEvidence
from trading.models.evaluation.evaluation_walk_forward_evidence import EvaluationWalkForwardEvidence
from trading.models.evaluation.strategy_evaluation_artifact import StrategyEvaluationArtifact

__all__ = [
    "EVALUATION_ARTIFACT_VERSION",
    "EVALUATION_SOURCE_MODE",
    "BacktestFreshness",
    "EvaluationBacktestEvidence",
    "EvaluationBasicScope",
    "EvaluationConfidence",
    "EvaluationDecisionScore",
    "EvaluationDiagnostics",
    "EvaluationMeta",
    "EvaluationPaperLiveEvidence",
    "EvaluationWalkForwardEvidence",
    "StrategyEvaluationArtifact",
]
