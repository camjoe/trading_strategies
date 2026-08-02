"""Promotion presentation helpers for operator-facing consumers.

Owns render/show helpers beneath the stable ``trading.services.promotion``
package surface.
"""

from __future__ import annotations

import sqlite3

from trading.models.evaluation import BacktestFreshness
from trading.models.promotion import PromotionAssessment
from trading.services.promotion.assessment import fetch_promotion_assessment
from trading.services.promotion.helpers import NONE_TEXT, render_bool, render_section
from trading.services.promotion.history import (
    PromotionReviewHistoryEntry,
    fetch_promotion_review_history,
)


def _format_backtest_freshness(freshness: BacktestFreshness | None) -> str:
    if freshness is None or not freshness.available or freshness.age_days is None:
        return NONE_TEXT
    label = "stale" if freshness.is_stale else "fresh"
    return f"{freshness.age_days:.1f} days ({label})"


def render_promotion_status_lines(assessment: PromotionAssessment) -> list[str]:
    lines = [
        "Promotion Status:",
        f"Account: {assessment.account_name}",
        f"Strategy: {assessment.strategy_name}",
        f"Stage: {assessment.stage}",
        f"Status: {assessment.status}",
        f"Ready for Live: {render_bool(assessment.ready_for_live)}",
        f"Live Trading Enabled: {render_bool(assessment.live_trading_enabled)}",
        f"Overall Confidence: {assessment.overall_confidence:.2f}",
        f"Evaluation Generated At: {assessment.evaluation_generated_at or NONE_TEXT}",
        f"Backtest Freshness: {_format_backtest_freshness(assessment.backtest_freshness)}",
        "Data Gaps: " + (", ".join(assessment.data_gaps) if assessment.data_gaps else NONE_TEXT),
        f"Next Action: {assessment.next_action}",
    ]
    lines.extend(render_section("Blockers", assessment.blockers))
    lines.extend(render_section("Warnings", assessment.warnings))
    return lines


def render_promotion_review_history_lines(entries: list[PromotionReviewHistoryEntry]) -> list[str]:
    lines = ["Promotion Review History:"]
    if not entries:
        lines.append(f"- {NONE_TEXT}")
        return lines

    for entry in entries:
        review = entry.review
        lines.extend(
            [
                (
                    f"Review #{review.id}: {review.account_name_snapshot}/{review.strategy_name} "
                    f"| state={review.review_state} | ready_for_live={render_bool(review.ready_for_live)}"
                ),
                f"Created: {review.created_at}",
                f"Updated: {review.updated_at}",
                f"Requested By: {review.requested_by or NONE_TEXT}",
                f"Reviewed By: {review.reviewed_by or NONE_TEXT}",
                f"Summary Note: {review.operator_summary_note or NONE_TEXT}",
            ]
        )
        if review.closed_at is not None:
            lines.append(f"Closed At: {review.closed_at}")
        lines.append("Events:")
        if not entry.events:
            lines.append(f"- {NONE_TEXT}")
            continue
        for event in entry.events:
            actor_text = event.actor_name or NONE_TEXT
            state_text = f"{event.from_review_state or NONE_TEXT} -> {event.to_review_state or NONE_TEXT}"
            lines.append(
                f"- [{event.event_seq}] {event.created_at} | {event.event_type}"
                f" | actor={actor_text} | state={state_text}"
            )
            if event.note is not None:
                lines.append(f"  note: {event.note}")
    return lines


def show_promotion_review_history(
    conn: sqlite3.Connection,
    account_name: str,
    strategy_name: str | None = None,
    *,
    limit: int = 10,
) -> list[PromotionReviewHistoryEntry]:
    entries = fetch_promotion_review_history(
        conn,
        account_name=account_name,
        strategy_name=strategy_name,
        limit=limit,
    )
    print("\n".join(render_promotion_review_history_lines(entries)))
    return entries


def show_promotion_status(
    conn: sqlite3.Connection,
    account_name: str,
    strategy_name: str | None = None,
) -> PromotionAssessment:
    assessment = fetch_promotion_assessment(
        conn,
        account_name=account_name,
        strategy_name=strategy_name,
    )
    print("\n".join(render_promotion_status_lines(assessment)))
    return assessment


__all__ = [
    "render_promotion_review_history_lines",
    "render_promotion_status_lines",
    "show_promotion_review_history",
    "show_promotion_status",
]
