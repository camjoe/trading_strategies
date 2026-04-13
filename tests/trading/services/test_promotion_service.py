import pytest

from trading.domain.promotion_models import PromotionAssessment
from trading.services.promotion_service import fetch_promotion_assessment, show_promotion_status


def test_fetch_promotion_assessment_uses_evaluation_service(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str | None]] = []

    def fake_fetch_strategy_evaluation(conn, *, account_name: str, strategy_name: str | None):
        from trading.domain.evaluation_models import (
            EvaluationBacktestEvidence,
            EvaluationBasicScope,
            EvaluationConfidence,
            EvaluationDiagnostics,
            EvaluationPaperLiveEvidence,
            EvaluationWalkForwardEvidence,
            StrategyEvaluationArtifact,
        )

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

    monkeypatch.setattr(
        "trading.services.promotion_service.fetch_strategy_evaluation",
        fake_fetch_strategy_evaluation,
    )

    assessment = fetch_promotion_assessment(
        object(),  # type: ignore[arg-type]
        account_name="acct_service",
        strategy_name="trend_v1",
    )

    assert calls == [("acct_service", "trend_v1")]
    assert assessment.stage == "promotion_review"
    assert assessment.ready_for_live is True


def test_show_promotion_status_prints_read_only_summary(
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    monkeypatch.setattr(
        "trading.services.promotion_service.fetch_promotion_assessment",
        lambda _conn, *, account_name, strategy_name=None: PromotionAssessment(
            account_name=account_name,
            strategy_name=strategy_name,
            stage="paper_observing",
            status="observing",
            ready_for_live=False,
            overall_confidence=0.55,
            data_gaps=["missing_paper_live_evidence"],
            blockers=["Paper evidence is required before manual promotion review."],
            warnings=[
                (
                    "Rotating accounts remain manual-only for final promotion, even "
                    "when automated checks pass."
                )
            ],
            next_action="Collect paper evidence before requesting manual promotion review.",
        ),
    )

    assessment = show_promotion_status(
        object(),  # type: ignore[arg-type]
        "acct_service",
        "trend_v1",
    )
    out = capsys.readouterr().out

    assert assessment.stage == "paper_observing"
    assert "Promotion Status:" in out
    assert "Account: acct_service" in out
    assert "Strategy: trend_v1" in out
    assert "Stage: paper_observing" in out
    assert "Ready for Live: no" in out
    assert "Data Gaps: missing_paper_live_evidence" in out
    assert "- Paper evidence is required before manual promotion review." in out
