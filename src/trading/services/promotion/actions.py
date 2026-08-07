"""Promotion mutation workflows for promotion consumers.

Owns persisted promotion-review request and closure flows beneath the stable
``trading.services.promotion`` package surface.
"""

from __future__ import annotations

import sqlite3
from dataclasses import replace

from common.time import utc_now_iso
from trading.domain.exceptions import NotFoundError
from trading.domain.strategies.resolution import validate_strategy_name
from trading.models.evaluation import StrategyEvaluationArtifact
from trading.models.promotion import (
    PromotionAssessment,
    PromotionReviewEventType,
    PromotionReviewRecord,
    PromotionReviewState,
)
from trading.repositories.promotion import PromotionReviewRepository
from trading.repositories.strategies import StrategyRepository
from trading.repositories.unit_of_work import unit_of_work
from trading.services.promotion.assessment import fetch_promotion_snapshot
from trading.services.promotion.helpers import normalize_optional_text

PROMOTION_REVIEW_ACTION_APPROVE = "approve"
PROMOTION_REVIEW_ACTION_REJECT = "reject"
PROMOTION_REVIEW_ACTION_NOTE = "note"

_fetch_promotion_snapshot = fetch_promotion_snapshot


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
    open_review = PromotionReviewRepository(conn).fetch_open(
        account_id=account_id,
        strategy_name=strategy_name,
    )
    if open_review is None:
        return
    raise ValueError(f"An open promotion review already exists for {account_name}/{strategy_name}.")


def _require_strategy_id(conn: sqlite3.Connection, *, strategy_name: str) -> int:
    strategy = StrategyRepository(conn).fetch_by_key(strategy_key=strategy_name)
    if strategy is None:
        raise ValueError(f"Promotion review request requires a strategy_id for '{strategy_name}'.")
    return strategy.id


def _fetch_review_or_raise(conn: sqlite3.Connection, *, review_id: int) -> PromotionReviewRecord:
    review = PromotionReviewRepository(conn).fetch_by_id(review_id=review_id)
    if review is None:
        raise NotFoundError(f"Promotion review {review_id} not found.")
    return review


def _record_review_event(
    conn: sqlite3.Connection,
    *,
    review_id: int,
    event_type: PromotionReviewEventType,
    actor_name: str | None,
    from_review_state: PromotionReviewState | None,
    to_review_state: PromotionReviewState | None,
    note: str | None,
    event_payload: dict[str, object],
    created_at: str,
) -> None:
    PromotionReviewRepository(conn).insert_event(
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
    expected_review_state: PromotionReviewState,
    review_state: PromotionReviewState,
    reviewed_by: str | None,
    operator_summary_note: str | None,
    updated_at: str,
    closed_at: str | None,
) -> PromotionReviewRecord:
    return PromotionReviewRepository(conn).update_review(
        review_id=review_id,
        expected_review_state=expected_review_state,
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
    artifact, assessment = _fetch_promotion_snapshot(
        conn,
        account_name=account_name,
        strategy_name=strategy_name,
    )
    account_id, resolved_strategy_name = _require_request_context(artifact, assessment)
    strategy_id = _require_strategy_id(conn, strategy_name=resolved_strategy_name)
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
    with unit_of_work(conn):
        repo = PromotionReviewRepository(conn)
        review = repo.insert_review(
            assessment=assessment,
            evaluation=artifact,
            strategy_id=strategy_id,
            requested_by=normalized_requested_by,
            operator_summary_note=normalized_note,
            created_at=created_at,
        )
        _record_review_event(
            conn,
            review_id=review.id,
            event_type=PromotionReviewEventType.REQUESTED,
            actor_name=normalized_requested_by,
            from_review_state=None,
            to_review_state=PromotionReviewState.REQUESTED,
            note=normalized_note,
            event_payload=_request_event_payload(assessment),
            created_at=created_at,
        )
        refreshed = repo.fetch_by_id(review_id=review.id)
    if refreshed is None:
        raise ValueError(f"Promotion review {review.id} not found after request creation.")
    return refreshed


def _require_open_review(conn: sqlite3.Connection, *, review_id: int) -> PromotionReviewRecord:
    review = _fetch_review_or_raise(conn, review_id=review_id)
    if review.review_state != PromotionReviewState.REQUESTED:
        raise ValueError(f"Promotion review {review_id} is already closed with state '{review.review_state}'.")
    return review


def _resolve_review_closure(
    action: str, *, ready_for_live: bool
) -> tuple[PromotionReviewState, PromotionReviewEventType]:
    if action == PROMOTION_REVIEW_ACTION_APPROVE:
        if not ready_for_live:
            raise ValueError("Only ready-for-live promotion reviews can be approved.")
        return PromotionReviewState.APPROVED, PromotionReviewEventType.APPROVED
    if action == PROMOTION_REVIEW_ACTION_REJECT:
        return PromotionReviewState.REJECTED, PromotionReviewEventType.REJECTED
    raise ValueError(f"Unsupported promotion review action '{action}'.")


def _execute_promotion_review_note(
    conn: sqlite3.Connection,
    *,
    review: PromotionReviewRecord,
    actor_name: str | None,
    note: str | None,
    updated_at: str,
) -> PromotionReviewRecord:
    with unit_of_work(conn):
        _record_review_event(
            conn,
            review_id=review.id,
            event_type=PromotionReviewEventType.NOTE_ADDED,
            actor_name=actor_name,
            from_review_state=review.review_state,
            to_review_state=review.review_state,
            note=note,
            event_payload={},
            created_at=updated_at,
        )
        return _update_review(
            conn,
            review_id=review.id,
            expected_review_state=PromotionReviewState.REQUESTED,
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

    with unit_of_work(conn):
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
            expected_review_state=review.review_state,
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
