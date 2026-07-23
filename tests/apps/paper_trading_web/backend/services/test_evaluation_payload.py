from __future__ import annotations

from paper_trading_web.backend.services.evaluation import (
    build_evaluation_detail_payload,
    build_evaluation_summary_payload,
)

from trading.models.evaluation import (
    BacktestFreshness,
    EvaluationBacktestEvidence,
    EvaluationConfidence,
    EvaluationDiagnostics,
    StrategyEvaluationArtifact,
)


def _artifact(freshness: BacktestFreshness | None) -> StrategyEvaluationArtifact:
    return StrategyEvaluationArtifact(
        backtest=EvaluationBacktestEvidence(available=True, total_return_pct=8.0),
        confidence=EvaluationConfidence(overall_confidence=0.5, blended_score=5.0),
        diagnostics=EvaluationDiagnostics(backtest_freshness=freshness),
    )


def test_summary_payload_marks_stale_backtest() -> None:
    stale = _artifact(BacktestFreshness(available=True, age_days=9.0, stale_threshold_days=3, is_stale=True))
    fresh = _artifact(BacktestFreshness(available=True, age_days=1.0, stale_threshold_days=3, is_stale=False))

    assert build_evaluation_summary_payload(stale)["backtestStale"] is True
    assert build_evaluation_summary_payload(fresh)["backtestStale"] is False


def test_summary_payload_backtest_stale_false_without_freshness() -> None:
    assert build_evaluation_summary_payload(_artifact(None))["backtestStale"] is False


def test_detail_payload_carries_freshness_object() -> None:
    artifact = _artifact(BacktestFreshness(available=True, age_days=6.0, stale_threshold_days=3, is_stale=True))

    freshness = build_evaluation_detail_payload(artifact)["backtestFreshness"]

    assert freshness == {"available": True, "ageDays": 6.0, "isStale": True, "staleThresholdDays": 3}


def test_detail_payload_freshness_unavailable_without_diagnostic() -> None:
    freshness = build_evaluation_detail_payload(_artifact(None))["backtestFreshness"]

    assert freshness == {"available": False, "ageDays": None, "isStale": False, "staleThresholdDays": None}
