import pytest

from trading.models.promotion import PromotionReviewEvent, PromotionReviewRecord
from trading.services.promotion import (
    render_promotion_review_history_lines,
    render_promotion_status_lines,
    show_promotion_review_history,
    show_promotion_status,
)
from trading.services.promotion import presentation as promotion_presentation
from trading.services.promotion.history import PromotionReviewHistoryEntry
from tests.support.promotion import make_observing_assessment


def test_render_promotion_status_lines_returns_read_only_summary() -> None:
    lines = render_promotion_status_lines(make_observing_assessment())

    joined = "\n".join(lines)
    assert "Promotion Status:" in joined
    assert "Account: acct_service" in joined
    assert "Stage: paper_observing" in joined
    assert "Data Gaps: missing_paper_live_evidence" in joined
    assert "- Paper evidence is required before manual promotion review." in joined
    # No backtest freshness on the observing fixture → none (P12 advisory line).
    assert "Backtest Freshness: none" in joined


def test_render_promotion_status_lines_shows_stale_backtest_freshness() -> None:
    from dataclasses import replace

    from trading.models.evaluation import BacktestFreshness

    assessment = replace(
        make_observing_assessment(),
        backtest_freshness=BacktestFreshness(available=True, age_days=6.0, stale_threshold_days=3, is_stale=True),
    )

    joined = "\n".join(render_promotion_status_lines(assessment))

    assert "Backtest Freshness: 6.0 days (stale)" in joined


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


def test_render_promotion_review_history_lines_includes_none_when_no_entries() -> None:
    assert render_promotion_review_history_lines([]) == ["Promotion Review History:", "- none"]


def test_render_promotion_review_history_lines_includes_none_when_entry_has_no_events() -> None:
    lines = render_promotion_review_history_lines(
        [
            PromotionReviewHistoryEntry(
                review=PromotionReviewRecord(
                    id=4,
                    account_name_snapshot="acct_service",
                    strategy_name="trend_v1",
                    review_state="requested",
                    ready_for_live=False,
                    created_at="2026-01-01T00:00:00Z",
                    updated_at="2026-01-02T00:00:00Z",
                ),
                events=[],
            )
        ]
    )

    assert "Events:" in lines
    assert "- none" in lines


def test_show_promotion_review_history_prints_and_returns_entries(
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    entries = [
        PromotionReviewHistoryEntry(
            review=PromotionReviewRecord(
                id=9,
                account_name_snapshot="acct_service",
                strategy_name="trend_v1",
                review_state="approved",
                ready_for_live=True,
                requested_by="cam",
                reviewed_by="reviewer",
                operator_summary_note="approved for manual promotion",
                created_at="2026-01-01T00:00:00Z",
                updated_at="2026-01-02T00:00:00Z",
                closed_at="2026-01-02T00:00:00Z",
            ),
            events=[
                PromotionReviewEvent(
                    event_seq=1,
                    event_type="approved",
                    actor_name="reviewer",
                    from_review_state="requested",
                    to_review_state="approved",
                    note="approved for manual promotion",
                    created_at="2026-01-02T00:00:00Z",
                )
            ],
        )
    ]
    monkeypatch.setattr(
        promotion_presentation,
        "fetch_promotion_review_history",
        lambda _conn, *, account_name, strategy_name=None, limit=10: entries,
    )

    returned = show_promotion_review_history(object(), "acct_service", "trend_v1", limit=5)
    out = capsys.readouterr().out

    assert returned == entries
    assert "Promotion Review History:" in out
    assert "Review #9: acct_service/trend_v1" in out
    assert "approved for manual promotion" in out


def test_render_promotion_review_history_lines_includes_closure_event_note(
    conn,
    promotion_account,  # noqa: ARG001
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
                status="ready_for_review",
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
