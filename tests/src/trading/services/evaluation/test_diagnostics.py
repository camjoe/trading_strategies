from __future__ import annotations

from trading.domain.evaluation.backtest_freshness import DEFAULT_BACKTEST_STALE_THRESHOLD_DAYS
from trading.models.evaluation import (
    EvaluationBacktestEvidence,
    EvaluationPaperLiveEvidence,
    EvaluationWalkForwardEvidence,
)
from trading.services.evaluation.evidence import build_diagnostics

_ABSENT = EvaluationBacktestEvidence(available=False)
_PAPER = EvaluationPaperLiveEvidence(available=True)
_WALK = EvaluationWalkForwardEvidence(available=True)


def _backtest(created_at: str) -> EvaluationBacktestEvidence:
    return EvaluationBacktestEvidence(available=True, created_at=created_at)


def test_diagnostics_report_fresh_backtest() -> None:
    diagnostics = build_diagnostics(
        backtest=_backtest("2026-03-15T00:00:00Z"),
        paper_live=_PAPER,
        walk_forward=_WALK,
        generated_at="2026-03-16T00:00:00Z",
    )

    assert diagnostics.data_gaps == []
    freshness = diagnostics.backtest_freshness
    assert freshness is not None
    assert freshness.available is True
    assert freshness.age_days == 1.0
    assert freshness.is_stale is False
    assert freshness.stale_threshold_days == DEFAULT_BACKTEST_STALE_THRESHOLD_DAYS


def test_diagnostics_report_stale_backtest() -> None:
    diagnostics = build_diagnostics(
        backtest=_backtest("2026-03-01T00:00:00Z"),
        paper_live=_PAPER,
        walk_forward=_WALK,
        generated_at="2026-03-16T00:00:00Z",
    )

    freshness = diagnostics.backtest_freshness
    assert freshness is not None
    assert freshness.age_days == 15.0
    assert freshness.is_stale is True


def test_diagnostics_freshness_unavailable_without_backtest() -> None:
    diagnostics = build_diagnostics(
        backtest=_ABSENT,
        paper_live=_PAPER,
        walk_forward=_WALK,
        generated_at="2026-03-16T00:00:00Z",
    )

    assert "missing_backtest_evidence" in diagnostics.data_gaps
    freshness = diagnostics.backtest_freshness
    assert freshness is not None
    assert freshness.available is False
    assert freshness.is_stale is False
