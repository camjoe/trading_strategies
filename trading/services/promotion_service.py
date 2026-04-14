from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from common.time import utc_now_iso
from trading.domain.evaluation_models import StrategyEvaluationArtifact
from trading.domain.promotion_models import (
    PROMOTION_REVIEW_EVENT_APPROVED,
    PROMOTION_REVIEW_EVENT_NOTE_ADDED,
    PROMOTION_REVIEW_EVENT_REJECTED,
    PROMOTION_REVIEW_EVENT_REQUESTED,
    PROMOTION_REVIEW_STATE_APPROVED,
    PROMOTION_REVIEW_STATE_REJECTED,
    PROMOTION_REVIEW_STATE_REQUESTED,
    PromotionAssessment,
    PromotionReviewEvent,
    PromotionReviewRecord,
)
from trading.domain.promotion_policy import assess_promotion_readiness
from trading.repositories.accounts_repository import fetch_account_by_name
from trading.repositories.promotion_repository import (
    fetch_open_promotion_review,
    fetch_promotion_review_by_id,
    fetch_promotion_review_events,
    fetch_promotion_reviews_for_account,
    insert_promotion_review,
    insert_promotion_review_event,
    update_promotion_review_record,
)
from trading.services.evaluation_service import fetch_strategy_evaluation

YES_TEXT = "yes"
NO_TEXT = "no"
NONE_TEXT = "none"

PROMOTION_REVIEW_ACTION_APPROVE = "approve"
PROMOTION_REVIEW_ACTION_REJECT = "reject"
PROMOTION_REVIEW_ACTION_NOTE = "note"


@dataclass(frozen=True)
class PromotionReviewHistoryEntry:
    review: PromotionReviewRecord
    events: list[PromotionReviewEvent]


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _fetch_current_promotion_snapshot(
    conn: sqlite3.Connection,
    *,
    account_name: str,
    strategy_name: str | None = None,
) -> tuple[StrategyEvaluationArtifact, PromotionAssessment]:
    artifact = fetch_strategy_evaluation(
        conn,
        account_name=account_name,
        strategy_name=strategy_name,
    )
    return artifact, assess_promotion_readiness(artifact)


def fetch_current_promotion_assessment(
    conn: sqlite3.Connection,
    *,
    account_name: str,
    strategy_name: str | None = None,
) -> PromotionAssessment:
    _, assessment = _fetch_current_promotion_snapshot(
        conn,
        account_name=account_name,
        strategy_name=strategy_name,
    )
    return assessment


def fetch_promotion_assessment(
    conn: sqlite3.Connection,
    *,
    account_name: str,
    strategy_name: str | None = None,
) -> PromotionAssessment:
    """Compatibility wrapper for the current computed promotion assessment.

    The promotion workflow is still read-only today, so this returns the
    current computed assessment rather than a persisted operator review record.
    """
    return fetch_current_promotion_assessment(
        conn,
        account_name=account_name,
        strategy_name=strategy_name,
    )


def _render_section(title: str, items: list[str]) -> list[str]:
    lines = [f"{title}:"]
    if not items:
        lines.append(f"- {NONE_TEXT}")
        return lines
    for item in items:
        lines.append(f"- {item}")
    return lines


def render_promotion_status_lines(assessment: PromotionAssessment) -> list[str]:
    lines = [
        "Promotion Status:",
        f"Account: {assessment.account_name}",
        f"Strategy: {assessment.strategy_name}",
        f"Stage: {assessment.stage}",
        f"Status: {assessment.status}",
        f"Ready for Live: {YES_TEXT if assessment.ready_for_live else NO_TEXT}",
        f"Live Trading Enabled: {YES_TEXT if assessment.live_trading_enabled else NO_TEXT}",
        f"Overall Confidence: {assessment.overall_confidence:.2f}",
        "Evaluation Generated At: "
        f"{assessment.evaluation_generated_at or NONE_TEXT}",
        "Data Gaps: "
        + (", ".join(assessment.data_gaps) if assessment.data_gaps else NONE_TEXT),
        f"Next Action: {assessment.next_action}",
    ]
    lines.extend(_render_section("Blockers", assessment.blockers))
    lines.extend(_render_section("Warnings", assessment.warnings))
    return lines


def execute_promotion_review_request(
    conn: sqlite3.Connection,
    *,
    account_name: str,
    strategy_name: str | None = None,
    requested_by: str | None = None,
    note: str | None = None,
) -> PromotionReviewRecord:
    artifact, assessment = _fetch_current_promotion_snapshot(
        conn,
        account_name=account_name,
        strategy_name=strategy_name,
    )
    if artifact.basic.account_id is None:
        raise ValueError("Promotion review request requires an account id in the evaluation artifact.")
    if artifact.basic.requested_strategy is None:
        raise ValueError("Promotion review request requires a resolved strategy in the evaluation artifact.")
    if assessment.live_trading_enabled:
        raise ValueError("Promotion review requests are only available before live trading is enabled.")

    open_review = fetch_open_promotion_review(
        conn,
        account_id=artifact.basic.account_id,
        strategy_name=artifact.basic.requested_strategy,
    )
    if open_review is not None:
        raise ValueError(
            "An open promotion review already exists for "
            f"{artifact.basic.account_name}/{artifact.basic.requested_strategy}."
        )

    created_at = utc_now_iso()
    normalized_requested_by = _normalize_optional_text(requested_by)
    normalized_note = _normalize_optional_text(note)
    with conn:
        review = insert_promotion_review(
            conn,
            assessment=assessment,
            evaluation=artifact,
            requested_by=normalized_requested_by,
            operator_summary_note=normalized_note,
            created_at=created_at,
        )
        insert_promotion_review_event(
            conn,
            review_id=int(review.id),
            event_type=PROMOTION_REVIEW_EVENT_REQUESTED,
            actor_name=normalized_requested_by,
            from_review_state=None,
            to_review_state=PROMOTION_REVIEW_STATE_REQUESTED,
            note=normalized_note,
            event_payload={
                "ready_for_live": assessment.ready_for_live,
                "assessment_stage": assessment.stage,
                "assessment_status": assessment.status,
                "overall_confidence": assessment.overall_confidence,
            },
            created_at=created_at,
        )
        refreshed = fetch_promotion_review_by_id(conn, review_id=int(review.id))
    if refreshed is None:
        raise ValueError(f"Promotion review {review.id} not found after request creation.")
    return refreshed


def _require_existing_review(conn: sqlite3.Connection, *, review_id: int) -> PromotionReviewRecord:
    review = fetch_promotion_review_by_id(conn, review_id=review_id)
    if review is None:
        raise ValueError(f"Promotion review {review_id} not found.")
    return review


def execute_promotion_review_action(
    conn: sqlite3.Connection,
    *,
    review_id: int,
    action: str,
    actor_name: str | None = None,
    note: str | None = None,
) -> PromotionReviewRecord:
    review = _require_existing_review(conn, review_id=review_id)
    if review.review_state != PROMOTION_REVIEW_STATE_REQUESTED:
        raise ValueError(f"Promotion review {review_id} is already closed with state '{review.review_state}'.")

    normalized_actor_name = _normalize_optional_text(actor_name)
    normalized_note = _normalize_optional_text(note)
    updated_at = utc_now_iso()

    if action == PROMOTION_REVIEW_ACTION_NOTE:
        with conn:
            insert_promotion_review_event(
                conn,
                review_id=review_id,
                event_type=PROMOTION_REVIEW_EVENT_NOTE_ADDED,
                actor_name=normalized_actor_name,
                from_review_state=review.review_state,
                to_review_state=review.review_state,
                note=normalized_note,
                event_payload={},
                created_at=updated_at,
            )
            return update_promotion_review_record(
                conn,
                review_id=review_id,
                review_state=review.review_state,
                reviewed_by=review.reviewed_by,
                operator_summary_note=normalized_note or review.operator_summary_note,
                updated_at=updated_at,
                closed_at=review.closed_at,
            )

    if action == PROMOTION_REVIEW_ACTION_APPROVE:
        if not review.ready_for_live:
            raise ValueError("Only ready-for-live promotion reviews can be approved.")
        next_state = PROMOTION_REVIEW_STATE_APPROVED
        event_type = PROMOTION_REVIEW_EVENT_APPROVED
    elif action == PROMOTION_REVIEW_ACTION_REJECT:
        next_state = PROMOTION_REVIEW_STATE_REJECTED
        event_type = PROMOTION_REVIEW_EVENT_REJECTED
    else:
        raise ValueError(f"Unsupported promotion review action '{action}'.")

    with conn:
        insert_promotion_review_event(
            conn,
            review_id=review_id,
            event_type=event_type,
            actor_name=normalized_actor_name,
            from_review_state=review.review_state,
            to_review_state=next_state,
            note=normalized_note,
            event_payload={},
            created_at=updated_at,
        )
        return update_promotion_review_record(
            conn,
            review_id=review_id,
            review_state=next_state,
            reviewed_by=normalized_actor_name or review.reviewed_by,
            operator_summary_note=normalized_note or review.operator_summary_note,
            updated_at=updated_at,
            closed_at=updated_at,
        )


def fetch_promotion_review_history(
    conn: sqlite3.Connection,
    *,
    account_name: str,
    strategy_name: str | None = None,
    limit: int = 10,
) -> list[PromotionReviewHistoryEntry]:
    if limit <= 0:
        raise ValueError("Promotion review history limit must be positive.")
    account = fetch_account_by_name(conn, account_name)
    if account is None:
        raise ValueError(f"Account '{account_name}' not found.")
    review_rows = fetch_promotion_reviews_for_account(
        conn,
        account_id=int(account["id"]),
        strategy_name=_normalize_optional_text(strategy_name),
        limit=limit,
    )
    return [
        PromotionReviewHistoryEntry(
            review=review,
            events=fetch_promotion_review_events(conn, review_id=int(review.id)),
        )
        for review in review_rows
    ]


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
                    f"| state={review.review_state} | ready_for_live={YES_TEXT if review.ready_for_live else NO_TEXT}"
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
            state_text = (
                f"{event.from_review_state or NONE_TEXT} -> {event.to_review_state or NONE_TEXT}"
            )
            lines.append(
                f"- [{event.event_seq}] {event.created_at} | {event.event_type} | actor={actor_text} | state={state_text}"
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
    assessment = fetch_current_promotion_assessment(
        conn,
        account_name=account_name,
        strategy_name=strategy_name,
    )
    print("\n".join(render_promotion_status_lines(assessment)))
    return assessment
