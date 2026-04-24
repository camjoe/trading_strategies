import pytest

from trading.services.promotion import (
    render_promotion_review_history_lines,
    render_promotion_status_lines,
    show_promotion_status,
)
from trading.services.promotion import presentation as promotion_presentation
from tests.support.promotion import make_observing_assessment


def test_render_promotion_status_lines_returns_read_only_summary() -> None:
    lines = render_promotion_status_lines(make_observing_assessment())

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
        promotion_presentation,
        "fetch_current_promotion_assessment",
        lambda _conn, *, account_name, strategy_name=None: make_observing_assessment(
            account_name=account_name,
            strategy_name=strategy_name,
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


def test_render_promotion_review_history_lines_includes_closure_event_note(
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
    from trading.services.promotion import actions as promotion_actions
    from trading.services.promotion import fetch_promotion_review_history
    from tests.support.promotion import make_ready_evaluation

    monkeypatch.setattr(
        promotion_actions,
        "_fetch_current_promotion_snapshot",
        lambda _conn, *, account_name, strategy_name=None: (
            make_ready_evaluation(account_name=account_name, strategy_name=strategy_name or "trend_v1"),
            promotion_actions.PromotionAssessment(
                account_name=account_name,
                strategy_name=strategy_name or "trend_v1",
                stage="promotion_review",
                status="ready",
                ready_for_live=True,
            ),
        ),
    )

    review = promotion_actions.execute_promotion_review_request(
        conn,
        account_name="acct_service",
        strategy_name="trend_v1",
        requested_by="cam",
    )
    promotion_actions.execute_promotion_review_action(
        conn,
        review_id=int(review.id),
        action="approve",
        actor_name="reviewer",
        note="approved for manual promotion",
    )

    lines = render_promotion_review_history_lines(fetch_promotion_review_history(conn, account_name="acct_service"))
    joined = "\n".join(lines)
    assert "approved" in joined
    assert "approved for manual promotion" in joined
