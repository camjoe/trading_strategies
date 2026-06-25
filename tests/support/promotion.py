from __future__ import annotations

from trading.models.evaluation import (
    EvaluationBacktestEvidence,
    EvaluationBasicScope,
    EvaluationConfidence,
    EvaluationDiagnostics,
    EvaluationPaperLiveEvidence,
    EvaluationWalkForwardEvidence,
    StrategyEvaluationArtifact,
)
from trading.models.promotion import PromotionAssessment


def make_ready_evaluation(
    *,
    account_name: str = "acct_service",
    strategy_name: str = "trend_v1",
    account_id: int = 1,
) -> StrategyEvaluationArtifact:
    return StrategyEvaluationArtifact(
        basic=EvaluationBasicScope(
            account_id=account_id,
            account_name=account_name,
            requested_strategy=strategy_name,
            live_trading_enabled=False,
        ),
        backtest=EvaluationBacktestEvidence(
            available=True,
            trade_count=12,
            snapshot_count=25,
            total_return_pct=5.0,
            max_drawdown_pct=-10.0,
        ),
        walk_forward=EvaluationWalkForwardEvidence(
            available=True,
            grouped=True,
            average_return_pct=1.0,
        ),
        paper_live=EvaluationPaperLiveEvidence(
            available=True,
            strategy_isolated=True,
            snapshot_count=12,
        ),
        confidence=EvaluationConfidence(overall_confidence=0.82),
        diagnostics=EvaluationDiagnostics(data_gaps=[]),
    )


def make_observing_assessment(
    *,
    account_name: str = "acct_service",
    strategy_name: str | None = "trend_v1",
) -> PromotionAssessment:
    return PromotionAssessment(
        account_name=account_name,
        strategy_name=strategy_name,
        stage="paper_observing",
        status="observing",
        ready_for_live=False,
        overall_confidence=0.55,
        data_gaps=["missing_paper_live_evidence"],
        blockers=["Paper evidence is required before manual promotion review."],
        warnings=[("Rotating accounts remain manual-only for final promotion, even when automated checks pass.")],
        next_action="Collect paper evidence before requesting manual promotion review.",
    )


__all__ = [
    "make_observing_assessment",
    "make_ready_evaluation",
]
