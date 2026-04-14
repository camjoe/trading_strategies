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
from trading.services.promotion_service import (
    execute_promotion_review_action,
    execute_promotion_review_request,
    fetch_current_promotion_assessment,
    fetch_promotion_assessment,
    fetch_promotion_review_history,
    render_promotion_review_history_lines,
    render_promotion_status_lines,
    show_promotion_status,
)


def test_fetch_current_promotion_assessment_uses_evaluation_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
        "trading.services.promotion_service.fetch_current_promotion_assessment",
        lambda _conn, *, account_name, strategy_name=None: expected,
    )

    assessment = fetch_promotion_assessment(
        object(),  # type: ignore[arg-type]
        account_name="acct_service",
        strategy_name="trend_v1",
    )

    assert assessment is expected


def test_render_promotion_status_lines_returns_read_only_summary() -> None:
    lines = render_promotion_status_lines(
        PromotionAssessment(
            account_name="acct_service",
            strategy_name="trend_v1",
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
        )
    )

    joined = "\n".join(lines)
    assert "Promotion Status:" in joined
    assert "Account: acct_service" in joined
    assert "Stage: paper_observing" in joined
    assert "Data Gaps: missing_paper_live_evidence" in joined
    assert "- Paper evidence is required before manual promotion review." in joined


def test_show_promotion_status_prints_read_only_summary(
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    monkeypatch.setattr(
        "trading.services.promotion_service.fetch_current_promotion_assessment",
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


def _ready_evaluation(*, account_name: str = "acct_service", strategy_name: str = "trend_v1") -> StrategyEvaluationArtifact:
    return StrategyEvaluationArtifact(
        basic=EvaluationBasicScope(
            account_id=1,
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


def test_execute_promotion_review_request_persists_frozen_snapshot(
    conn,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn.execute(
        """
        INSERT INTO accounts (id, name, strategy, initial_cash, benchmark_ticker, created_at)
        VALUES (1, 'acct_service', 'trend_v1', 1000, 'SPY', '2026-01-01T00:00:00Z')
        """
    )
    conn.commit()
    monkeypatch.setattr(
        "trading.services.promotion_service.fetch_strategy_evaluation",
        lambda _conn, *, account_name, strategy_name=None: _ready_evaluation(
            account_name=account_name,
            strategy_name=strategy_name or "trend_v1",
        ),
    )

    review = execute_promotion_review_request(
        conn,
        account_name="acct_service",
        strategy_name="trend_v1",
        requested_by="cam",
        note="please review",
    )

    assert review.account_name_snapshot == "acct_service"
    assert review.review_state == "requested"
    assert review.requested_by == "cam"
    assert review.ready_for_live is True

    entries = fetch_promotion_review_history(conn, account_name="acct_service")
    assert len(entries) == 1
    assert entries[0].events[0].event_type == "requested"
    assert entries[0].events[0].note == "please review"


def test_execute_promotion_review_action_closes_open_review(
    conn,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn.execute(
        """
        INSERT INTO accounts (id, name, strategy, initial_cash, benchmark_ticker, created_at)
        VALUES (1, 'acct_service', 'trend_v1', 1000, 'SPY', '2026-01-01T00:00:00Z')
        """
    )
    conn.commit()
    monkeypatch.setattr(
        "trading.services.promotion_service.fetch_strategy_evaluation",
        lambda _conn, *, account_name, strategy_name=None: _ready_evaluation(
            account_name=account_name,
            strategy_name=strategy_name or "trend_v1",
        ),
    )
    review = execute_promotion_review_request(conn, account_name="acct_service", requested_by="cam")

    updated = execute_promotion_review_action(
        conn,
        review_id=int(review.id),
        action="approve",
        actor_name="reviewer",
        note="approved for manual promotion",
    )

    assert updated.review_state == "approved"
    assert updated.reviewed_by == "reviewer"
    assert updated.closed_at is not None
    lines = render_promotion_review_history_lines(fetch_promotion_review_history(conn, account_name="acct_service"))
    joined = "\n".join(lines)
    assert "approved" in joined
    assert "approved for manual promotion" in joined
