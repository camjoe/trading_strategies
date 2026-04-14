from __future__ import annotations

import sqlite3
from dataclasses import dataclass, replace

from common.time import utc_now_iso
from trading.backtesting.domain.strategy_signals import validate_strategy_name
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


def _render_bool(value: bool) -> str:
    return YES_TEXT if value else NO_TEXT


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
        f"Ready for Live: {_render_bool(assessment.ready_for_live)}",
        f"Live Trading Enabled: {_render_bool(assessment.live_trading_enabled)}",
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


def _require_request_context(
    artifact: StrategyEvaluationArtifact,
    assessment: PromotionAssessment,
) -> tuple[int, str]:
    account_id = artifact.basic.account_id
    if account_id is None:
        raise ValueError("Promotion review request requires an account id in the evaluation artifact.")

    strategy_name = artifact.basic.requested_strategy
    if strategy_name is None:
        raise ValueError("Promotion review request requires a resolved strategy in the evaluation artifact.")
    strategy_name = validate_strategy_name(strategy_name)

    if assessment.live_trading_enabled:
        raise ValueError("Promotion review requests are only available before live trading is enabled.")

    return account_id, strategy_name


def _ensure_no_open_review_for_request(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    strategy_name: str,
    account_name: str,
) -> None:
    open_review = fetch_open_promotion_review(
        conn,
        account_id=account_id,
        strategy_name=strategy_name,
    )
    if open_review is None:
        return
    raise ValueError(
        "An open promotion review already exists for "
        f"{account_name}/{strategy_name}."
    )


def _fetch_review_or_raise(conn: sqlite3.Connection, *, review_id: int) -> PromotionReviewRecord:
    review = fetch_promotion_review_by_id(conn, review_id=review_id)
    if review is None:
        raise ValueError(f"Promotion review {review_id} not found.")
    return review


def _record_review_event(
    conn: sqlite3.Connection,
    *,
    review_id: int,
    event_type: str,
    actor_name: str | None,
    from_review_state: str | None,
    to_review_state: str | None,
    note: str | None,
    event_payload: dict[str, object],
    created_at: str,
) -> None:
    insert_promotion_review_event(
        conn,
        review_id=review_id,
        event_type=event_type,
        actor_name=actor_name,
        from_review_state=from_review_state,
        to_review_state=to_review_state,
        note=note,
        event_payload=event_payload,
        created_at=created_at,
    )


def _update_review(
    conn: sqlite3.Connection,
    *,
    review_id: int,
    review_state: str,
    reviewed_by: str | None,
    operator_summary_note: str | None,
    updated_at: str,
    closed_at: str | None,
) -> PromotionReviewRecord:
    return update_promotion_review_record(
        conn,
        review_id=review_id,
        review_state=review_state,
        reviewed_by=reviewed_by,
        operator_summary_note=operator_summary_note,
        updated_at=updated_at,
        closed_at=closed_at,
    )


def _request_event_payload(assessment: PromotionAssessment) -> dict[str, object]:
    return {
        "ready_for_live": assessment.ready_for_live,
        "assessment_stage": assessment.stage,
        "assessment_status": assessment.status,
        "overall_confidence": assessment.overall_confidence,
    }


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
    account_id, resolved_strategy_name = _require_request_context(artifact, assessment)
    artifact = replace(
        artifact,
        basic=replace(artifact.basic, requested_strategy=resolved_strategy_name),
    )
    assessment = replace(assessment, strategy_name=resolved_strategy_name)

    _ensure_no_open_review_for_request(
        conn,
        account_id=account_id,
        strategy_name=resolved_strategy_name,
        account_name=artifact.basic.account_name or account_name,
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
        _record_review_event(
            conn,
            review_id=int(review.id),
            event_type=PROMOTION_REVIEW_EVENT_REQUESTED,
            actor_name=normalized_requested_by,
            from_review_state=None,
            to_review_state=PROMOTION_REVIEW_STATE_REQUESTED,
            note=normalized_note,
            event_payload=_request_event_payload(assessment),
            created_at=created_at,
        )
        refreshed = fetch_promotion_review_by_id(conn, review_id=int(review.id))
    if refreshed is None:
        raise ValueError(f"Promotion review {review.id} not found after request creation.")
    return refreshed


def _require_open_review(conn: sqlite3.Connection, *, review_id: int) -> PromotionReviewRecord:
    review = _fetch_review_or_raise(conn, review_id=review_id)
    if review.review_state != PROMOTION_REVIEW_STATE_REQUESTED:
        raise ValueError(f"Promotion review {review_id} is already closed with state '{review.review_state}'.")
    return review


def _resolve_review_closure(action: str, *, ready_for_live: bool) -> tuple[str, str]:
    if action == PROMOTION_REVIEW_ACTION_APPROVE:
        if not ready_for_live:
            raise ValueError("Only ready-for-live promotion reviews can be approved.")
        return PROMOTION_REVIEW_STATE_APPROVED, PROMOTION_REVIEW_EVENT_APPROVED
    if action == PROMOTION_REVIEW_ACTION_REJECT:
        return PROMOTION_REVIEW_STATE_REJECTED, PROMOTION_REVIEW_EVENT_REJECTED
    raise ValueError(f"Unsupported promotion review action '{action}'.")


def _execute_promotion_review_note(
    conn: sqlite3.Connection,
    *,
    review: PromotionReviewRecord,
    actor_name: str | None,
    note: str | None,
    updated_at: str,
) -> PromotionReviewRecord:
    with conn:
        _record_review_event(
            conn,
            review_id=int(review.id),
            event_type=PROMOTION_REVIEW_EVENT_NOTE_ADDED,
            actor_name=actor_name,
            from_review_state=review.review_state,
            to_review_state=review.review_state,
            note=note,
            event_payload={},
            created_at=updated_at,
        )
        return _update_review(
            conn,
            review_id=int(review.id),
            review_state=review.review_state,
            reviewed_by=review.reviewed_by,
            operator_summary_note=note or review.operator_summary_note,
            updated_at=updated_at,
            closed_at=review.closed_at,
        )


def execute_promotion_review_action(
    conn: sqlite3.Connection,
    *,
    review_id: int,
    action: str,
    actor_name: str | None = None,
    note: str | None = None,
) -> PromotionReviewRecord:
    review = _require_open_review(conn, review_id=review_id)

    normalized_actor_name = _normalize_optional_text(actor_name)
    normalized_note = _normalize_optional_text(note)
    updated_at = utc_now_iso()

    if action == PROMOTION_REVIEW_ACTION_NOTE:
        return _execute_promotion_review_note(
            conn,
            review=review,
            actor_name=normalized_actor_name,
            note=normalized_note,
            updated_at=updated_at,
        )

    next_state, event_type = _resolve_review_closure(action, ready_for_live=review.ready_for_live)

    with conn:
        _record_review_event(
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
        return _update_review(
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
                    f"| state={review.review_state} | ready_for_live={_render_bool(review.ready_for_live)}"
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
