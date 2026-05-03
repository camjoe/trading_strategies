import pytest

from trading.domain.evaluation_models import (
    EvaluationBacktestEvidence,
    EvaluationBasicScope,
    EvaluationConfidence,
    EvaluationDiagnostics,
    EvaluationPaperLiveEvidence,
    EvaluationWalkForwardEvidence,
    StrategyEvaluationArtifact,
)
from trading.domain.promotion_models import PromotionAssessment
from trading.services.promotion import fetch_current_promotion_assessment, fetch_promotion_assessment
from trading.services.promotion import assessment as promotion_assessment


def test_fetch_current_promotion_assessment_uses_evaluation_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str | None]] = []

    def fake_fetch_strategy_evaluation(conn, *, account_name: str, strategy_name: str | None):
        calls.append((account_name, strategy_name))
        return StrategyEvaluationArtifact(
            basic=EvaluationBasicScope(
                account_name=account_name,
                requested_strategy=strategy_name,
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
            confidence=EvaluationConfidence(overall_confidence=0.7),
            diagnostics=EvaluationDiagnostics(data_gaps=[]),
        )

    monkeypatch.setattr(promotion_assessment, "fetch_strategy_evaluation", fake_fetch_strategy_evaluation)

    assessment = fetch_current_promotion_assessment(
        object(),  # type: ignore[arg-type]
        account_name="acct_service",
        strategy_name="trend_v1",
    )

    assert calls == [("acct_service", "trend_v1")]
    assert assessment.stage == "promotion_review"
    assert assessment.ready_for_live is True


def test_fetch_promotion_assessment_wraps_current_assessment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = PromotionAssessment(account_name="acct_service", strategy_name="trend_v1")
    monkeypatch.setattr(
        promotion_assessment,
        "fetch_current_promotion_assessment",
        lambda _conn, *, account_name, strategy_name=None: expected,
    )

    assessment = fetch_promotion_assessment(
        object(),  # type: ignore[arg-type]
        account_name="acct_service",
        strategy_name="trend_v1",
    )

    assert assessment is expected
