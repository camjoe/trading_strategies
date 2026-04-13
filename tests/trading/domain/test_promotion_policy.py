from trading.domain.evaluation_models import (
    EvaluationBacktestEvidence,
    EvaluationBasicScope,
    EvaluationConfidence,
    EvaluationDiagnostics,
    EvaluationMeta,
    EvaluationPaperLiveEvidence,
    EvaluationWalkForwardEvidence,
    StrategyEvaluationArtifact,
)
from trading.domain.promotion_policy import assess_promotion_readiness


def _artifact(
    *,
    live_trading_enabled: bool = False,
    rotation_enabled: bool = False,
    backtest_available: bool = True,
    trade_count: int | None = 12,
    backtest_snapshot_count: int | None = 25,
    backtest_return_pct: float | None = 6.0,
    max_drawdown_pct: float | None = -10.0,
    walk_forward_available: bool = True,
    walk_forward_grouped: bool = True,
    walk_forward_average_return_pct: float | None = 2.0,
    paper_available: bool = False,
    paper_strategy_isolated: bool = True,
    paper_snapshot_count: int | None = None,
    overall_confidence: float = 0.65,
    data_gaps: list[str] | None = None,
    backtest_warnings: str | None = None,
) -> StrategyEvaluationArtifact:
    return StrategyEvaluationArtifact(
        meta=EvaluationMeta(generated_at="2026-05-01T00:00:00Z"),
        basic=EvaluationBasicScope(
            account_name="acct_promo",
            requested_strategy="trend_v1",
            rotation_enabled=rotation_enabled,
            live_trading_enabled=live_trading_enabled,
        ),
        backtest=EvaluationBacktestEvidence(
            available=backtest_available,
            trade_count=trade_count,
            snapshot_count=backtest_snapshot_count,
            total_return_pct=backtest_return_pct,
            max_drawdown_pct=max_drawdown_pct,
            warnings=backtest_warnings,
        ),
        walk_forward=EvaluationWalkForwardEvidence(
            available=walk_forward_available,
            grouped=walk_forward_grouped,
            average_return_pct=walk_forward_average_return_pct,
        ),
        paper_live=EvaluationPaperLiveEvidence(
            available=paper_available,
            strategy_isolated=paper_strategy_isolated,
            snapshot_count=paper_snapshot_count,
        ),
        confidence=EvaluationConfidence(overall_confidence=overall_confidence),
        diagnostics=EvaluationDiagnostics(data_gaps=list(data_gaps or [])),
    )


def test_assess_promotion_readiness_stays_candidate_when_research_is_missing() -> None:
    assessment = assess_promotion_readiness(
        _artifact(
            backtest_available=False,
            walk_forward_available=False,
        )
    )

    assert assessment.stage == "candidate"
    assert assessment.status == "blocked"
    assert assessment.ready_for_live is False
    assert "Backtest evidence is required for promotion assessment." in assessment.blockers
    assert assessment.next_action == "Produce research evidence that meets promotion thresholds."


def test_assess_promotion_readiness_requires_strategy_isolated_rotation_paper_evidence() -> None:
    assessment = assess_promotion_readiness(
        _artifact(
            rotation_enabled=True,
            paper_available=False,
            paper_strategy_isolated=False,
            overall_confidence=0.72,
            data_gaps=[],
        )
    )

    assert assessment.stage == "research_validated"
    assert assessment.status == "observing"
    assert assessment.ready_for_live is False
    assert (
        "Rotating accounts require strategy-isolated paper evidence before manual promotion review."
        in assessment.blockers
    )
    assert (
        "Rotating accounts remain manual-only for final promotion, even when automated checks pass."
        in assessment.warnings
    )


def test_assess_promotion_readiness_marks_promotion_review_when_all_gates_pass() -> None:
    assessment = assess_promotion_readiness(
        _artifact(
            paper_available=True,
            paper_snapshot_count=12,
            overall_confidence=0.72,
            data_gaps=[],
            backtest_warnings="seeded warning",
        )
    )

    assert assessment.stage == "promotion_review"
    assert assessment.status == "ready_for_review"
    assert assessment.ready_for_live is True
    assert assessment.blockers == []
    assert "Backtest warnings: seeded warning" in assessment.warnings


def test_assess_promotion_readiness_marks_live_accounts_as_live_active() -> None:
    assessment = assess_promotion_readiness(
        _artifact(
            live_trading_enabled=True,
            paper_available=True,
            paper_snapshot_count=12,
        )
    )

    assert assessment.stage == "live_active"
    assert assessment.status == "live"
    assert assessment.ready_for_live is False
    assert assessment.blockers == []
    assert any("already enabled" in warning for warning in assessment.warnings)
