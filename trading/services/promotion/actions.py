"""Promotion mutation workflows for promotion consumers.

Owns persisted promotion-review request and closure flows beneath the stable
``trading.services.promotion`` package surface.
"""

from __future__ import annotations

import sqlite3
from dataclasses import replace

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
    PromotionReviewRecord,
)
from trading.repositories.promotion import (
    fetch_open_promotion_review,
    fetch_promotion_review_by_id,
    insert_promotion_review,
    insert_promotion_review_event,
    update_promotion_review_record,
)
from trading.services.promotion._shared import normalize_optional_text
from trading.services.promotion.assessment import _fetch_current_promotion_snapshot

PROMOTION_REVIEW_ACTION_APPROVE = "approve"
PROMOTION_REVIEW_ACTION_REJECT = "reject"
PROMOTION_REVIEW_ACTION_NOTE = "note"


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
    normalized_requested_by = normalize_optional_text(requested_by)
    normalized_note = normalize_optional_text(note)
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

    normalized_actor_name = normalize_optional_text(actor_name)
    normalized_note = normalize_optional_text(note)
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


__all__ = [
    "PROMOTION_REVIEW_ACTION_APPROVE",
    "PROMOTION_REVIEW_ACTION_NOTE",
    "PROMOTION_REVIEW_ACTION_REJECT",
    "execute_promotion_review_action",
    "execute_promotion_review_request",
]
