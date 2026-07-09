"""P2/1c — cross-surface regression: compare, promotion, and rotation all read the same
decision-score contract (`derive_decision_score`) and handle missing evidence identically.

See docs/implementation/p2-evaluation-contract-tests.md.
"""

from __future__ import annotations

import pytest

from paper_trading_web.backend.services.evaluation import build_evaluation_summary_payload
from trading.domain.evaluation_decision_score import derive_decision_score
from trading.domain.promotion_policy import assess_promotion_readiness
from trading.models.evaluation import (
    EvaluationBacktestEvidence,
    EvaluationConfidence,
    EvaluationDiagnostics,
    StrategyEvaluationArtifact,
)
from trading.services.books.rotation_metrics import build_rotation_strategy_metrics

_ROTATION_FETCH_TARGET = "trading.services.books.rotation_metrics.fetch_strategy_evaluation_for_account_row"


def _artifact(
    *,
    blended_score: float | None,
    backtest_confidence: float,
    paper_live_confidence: float,
    overall_confidence: float,
    backtest_available: bool,
    backtest_trade_count: int,
    data_gaps: list[str],
) -> StrategyEvaluationArtifact:
    return StrategyEvaluationArtifact(
        backtest=EvaluationBacktestEvidence(available=backtest_available, trade_count=backtest_trade_count),
        confidence=EvaluationConfidence(
            backtest_confidence=backtest_confidence,
            paper_live_confidence=paper_live_confidence,
            overall_confidence=overall_confidence,
            blended_score=blended_score,
        ),
        diagnostics=EvaluationDiagnostics(data_gaps=data_gaps),
    )


_SCENARIOS = {
    "complete": _artifact(
        blended_score=8.0,
        backtest_confidence=0.6,
        paper_live_confidence=0.4,
        overall_confidence=0.5,
        backtest_available=True,
        backtest_trade_count=20,
        data_gaps=[],
    ),
    "missing_backtest": _artifact(
        blended_score=3.0,
        backtest_confidence=0.0,
        paper_live_confidence=0.5,
        overall_confidence=0.2,
        backtest_available=False,
        backtest_trade_count=0,
        data_gaps=["missing_backtest_evidence"],
    ),
    "missing_paper_live": _artifact(
        blended_score=6.0,
        backtest_confidence=0.6,
        paper_live_confidence=0.0,
        overall_confidence=0.3,
        backtest_available=True,
        backtest_trade_count=15,
        data_gaps=["missing_paper_live_evidence"],
    ),
    "null_score": _artifact(
        blended_score=None,
        backtest_confidence=0.0,
        paper_live_confidence=0.0,
        overall_confidence=0.0,
        backtest_available=False,
        backtest_trade_count=0,
        data_gaps=["missing_backtest_evidence", "missing_paper_live_evidence"],
    ),
}


@pytest.mark.parametrize("scenario", list(_SCENARIOS))
def test_compare_payload_matches_contract(scenario: str) -> None:
    artifact = _SCENARIOS[scenario]
    decision = derive_decision_score(artifact)

    payload = build_evaluation_summary_payload(artifact)

    assert payload["blendedScore"] == decision.score
    assert payload["overallConfidence"] == decision.confidence
    assert payload["backtestConfidence"] == decision.backtest_confidence
    assert payload["paperLiveConfidence"] == decision.paper_live_confidence
    assert payload["dataGaps"] == list(decision.data_gaps)


@pytest.mark.parametrize("scenario", list(_SCENARIOS))
def test_promotion_reads_same_confidence_and_gaps(scenario: str) -> None:
    artifact = _SCENARIOS[scenario]
    decision = derive_decision_score(artifact)

    assessment = assess_promotion_readiness(artifact)

    assert assessment.overall_confidence == decision.confidence
    assert list(assessment.data_gaps) == list(decision.data_gaps)


@pytest.mark.parametrize("scenario", list(_SCENARIOS))
def test_rotation_metrics_use_same_contract(scenario: str, monkeypatch) -> None:
    artifact = _SCENARIOS[scenario]
    decision = derive_decision_score(artifact)
    monkeypatch.setattr(_ROTATION_FETCH_TARGET, lambda _conn, _account, *, strategy_name: artifact)

    # conn and account are only forwarded to the (monkeypatched) fetch, so placeholders suffice.
    metrics = build_rotation_strategy_metrics(
        object(),
        account=object(),
        strategy_name="any",
        param_set_id=None,
    )

    expected_score = decision.score if decision.score is not None else 0.0
    assert metrics.risk_adjusted_return == expected_score
    assert metrics.trade_count == (artifact.backtest.trade_count or 0)
