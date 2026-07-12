from __future__ import annotations

from trading.domain.evaluation_decision_score import derive_decision_score
from trading.models.evaluation import (
    EvaluationConfidence,
    EvaluationDiagnostics,
    StrategyEvaluationArtifact,
)


def _artifact(
    *,
    blended_score: float | None,
    overall_confidence: float,
    backtest_confidence: float,
    paper_live_confidence: float,
    data_gaps: list[str],
) -> StrategyEvaluationArtifact:
    return StrategyEvaluationArtifact(
        confidence=EvaluationConfidence(
            backtest_confidence=backtest_confidence,
            paper_live_confidence=paper_live_confidence,
            overall_confidence=overall_confidence,
            blended_score=blended_score,
        ),
        diagnostics=EvaluationDiagnostics(data_gaps=data_gaps),
    )


def test_complete_evidence_carries_score_and_confidence() -> None:
    artifact = _artifact(
        blended_score=8.0,
        overall_confidence=0.5,
        backtest_confidence=0.6,
        paper_live_confidence=0.4,
        data_gaps=[],
    )

    decision = derive_decision_score(artifact)

    assert decision.score == 8.0
    assert decision.has_evidence is True
    assert decision.confidence == 0.5
    assert decision.backtest_confidence == 0.6
    assert decision.paper_live_confidence == 0.4
    assert decision.data_gaps == ()


def test_missing_backtest_evidence_keeps_score_and_reports_gap() -> None:
    artifact = _artifact(
        blended_score=3.0,
        overall_confidence=0.2,
        backtest_confidence=0.0,
        paper_live_confidence=0.5,
        data_gaps=["missing_backtest_evidence"],
    )

    decision = derive_decision_score(artifact)

    assert decision.score == 3.0
    assert decision.has_evidence is True
    assert decision.backtest_confidence == 0.0
    assert decision.data_gaps == ("missing_backtest_evidence",)


def test_missing_paper_live_evidence_keeps_score_and_reports_gap() -> None:
    artifact = _artifact(
        blended_score=6.0,
        overall_confidence=0.3,
        backtest_confidence=0.6,
        paper_live_confidence=0.0,
        data_gaps=["missing_paper_live_evidence"],
    )

    decision = derive_decision_score(artifact)

    assert decision.score == 6.0
    assert decision.has_evidence is True
    assert decision.paper_live_confidence == 0.0
    assert decision.data_gaps == ("missing_paper_live_evidence",)


def test_null_blended_score_marks_absent_evidence() -> None:
    artifact = _artifact(
        blended_score=None,
        overall_confidence=0.0,
        backtest_confidence=0.0,
        paper_live_confidence=0.0,
        data_gaps=["missing_backtest_evidence", "missing_paper_live_evidence"],
    )

    decision = derive_decision_score(artifact)

    assert decision.score is None
    assert decision.has_evidence is False
    assert decision.confidence == 0.0
    assert decision.data_gaps == (
        "missing_backtest_evidence",
        "missing_paper_live_evidence",
    )


def test_backtest_freshness_does_not_affect_decision_score() -> None:
    # Freshness is advisory-only (P12): it must never change the derived score.
    from dataclasses import replace

    from trading.models.evaluation import BacktestFreshness

    base = _artifact(
        blended_score=8.0,
        overall_confidence=0.5,
        backtest_confidence=0.6,
        paper_live_confidence=0.4,
        data_gaps=[],
    )
    stale = replace(
        base,
        diagnostics=replace(
            base.diagnostics,
            backtest_freshness=BacktestFreshness(available=True, age_days=99.0, stale_threshold_days=3, is_stale=True),
        ),
    )

    assert derive_decision_score(stale) == derive_decision_score(base)
