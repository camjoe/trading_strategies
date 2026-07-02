"""Adapter from the evaluation artifact to a decision-ready score contract.

Pure transform with no I/O. This is the single place that turns a
``StrategyEvaluationArtifact`` into the ``EvaluationDecisionScore`` consumed by
decision surfaces (compare, promotion, and — from 1b — sleeve rotation), so
those surfaces stop reading evaluation confidence fields directly.
"""

from __future__ import annotations

from trading.models.evaluation import EvaluationDecisionScore, StrategyEvaluationArtifact


def derive_decision_score(artifact: StrategyEvaluationArtifact) -> EvaluationDecisionScore:
    confidence = artifact.confidence
    score = confidence.blended_score
    return EvaluationDecisionScore(
        score=score,
        confidence=confidence.overall_confidence,
        backtest_confidence=confidence.backtest_confidence,
        paper_live_confidence=confidence.paper_live_confidence,
        has_evidence=score is not None,
        data_gaps=tuple(artifact.diagnostics.data_gaps),
    )
