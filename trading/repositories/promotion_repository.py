from __future__ import annotations

import json
import sqlite3

from trading.domain.evaluation_models import StrategyEvaluationArtifact
from trading.domain.promotion_models import (
    PROMOTION_REVIEW_ACTOR_TYPE_OPERATOR,
    PROMOTION_REVIEW_STATE_REQUESTED,
    PromotionAssessment,
    PromotionReviewEvent,
    PromotionReviewRecord,
)


def _row_text(row: sqlite3.Row, key: str) -> str | None:
    value = row[key]
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _row_json_object(row: sqlite3.Row, key: str) -> dict[str, object]:
    raw = row[key]
    if raw is None:
        return {}
    payload = json.loads(str(raw))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in column '{key}'.")
    return payload


def _map_review_row(row: sqlite3.Row) -> PromotionReviewRecord:
    return PromotionReviewRecord(
        id=int(row["id"]),
        account_id=int(row["account_id"]),
        account_name_snapshot=str(row["account_name_snapshot"]),
        strategy_name=str(row["strategy_name"]),
        review_state=str(row["review_state"]),
        assessment_stage=str(row["assessment_stage"]),
        assessment_status=str(row["assessment_status"]),
        ready_for_live=bool(int(row["ready_for_live"])),
        overall_confidence=float(row["overall_confidence"]),
        live_trading_enabled_snapshot=bool(int(row["live_trading_enabled_snapshot"])),
        promotion_assessment_version=str(row["promotion_assessment_version"]),
        evaluation_artifact_version=str(row["evaluation_artifact_version"]),
        frozen_assessment_payload=_row_json_object(row, "frozen_assessment_payload"),
        frozen_evaluation_payload=_row_json_object(row, "frozen_evaluation_payload"),
        requested_by=_row_text(row, "requested_by"),
        reviewed_by=_row_text(row, "reviewed_by"),
        operator_summary_note=_row_text(row, "operator_summary_note"),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        closed_at=_row_text(row, "closed_at"),
    )


def _map_event_row(row: sqlite3.Row) -> PromotionReviewEvent:
    return PromotionReviewEvent(
        id=int(row["id"]),
        review_id=int(row["review_id"]),
        event_seq=int(row["event_seq"]),
        event_type=str(row["event_type"]),
        actor_type=str(row["actor_type"]),
        actor_name=_row_text(row, "actor_name"),
        from_review_state=_row_text(row, "from_review_state"),
        to_review_state=_row_text(row, "to_review_state"),
        note=_row_text(row, "note"),
        event_payload=_row_json_object(row, "event_payload"),
        created_at=str(row["created_at"]),
    )


def insert_promotion_review(
    conn: sqlite3.Connection,
    *,
    assessment: PromotionAssessment,
    evaluation: StrategyEvaluationArtifact,
    requested_by: str | None,
    operator_summary_note: str | None,
    created_at: str,
) -> PromotionReviewRecord:
    if evaluation.basic.account_id is None:
        raise ValueError("Promotion review requires evaluation.basic.account_id.")
    if evaluation.basic.account_name is None:
        raise ValueError("Promotion review requires evaluation.basic.account_name.")
    if evaluation.basic.requested_strategy is None:
        raise ValueError("Promotion review requires evaluation.basic.requested_strategy.")

    cursor = conn.execute(
        """
        INSERT INTO promotion_reviews (
            account_id,
            account_name_snapshot,
            strategy_name,
            review_state,
            assessment_stage,
            assessment_status,
            ready_for_live,
            overall_confidence,
            live_trading_enabled_snapshot,
            promotion_assessment_version,
            evaluation_artifact_version,
            frozen_assessment_payload,
            frozen_evaluation_payload,
            requested_by,
            reviewed_by,
            operator_summary_note,
            created_at,
            updated_at,
            closed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            evaluation.basic.account_id,
            evaluation.basic.account_name,
            evaluation.basic.requested_strategy,
            PROMOTION_REVIEW_STATE_REQUESTED,
            assessment.stage,
            assessment.status,
            int(assessment.ready_for_live),
            assessment.overall_confidence,
            int(assessment.live_trading_enabled),
            assessment.version,
            evaluation.meta.artifact_version,
            json.dumps(assessment.to_payload(), separators=(",", ":"), sort_keys=True),
            json.dumps(evaluation.to_payload(), separators=(",", ":"), sort_keys=True),
            requested_by,
            None,
            operator_summary_note or "",
            created_at,
            created_at,
            None,
        ),
    )
    review_id = cursor.lastrowid
    if not isinstance(review_id, int):
        raise ValueError("Expected integer promotion review id after insert.")
    review = fetch_promotion_review_by_id(conn, review_id=review_id)
    if review is None:
        raise ValueError(f"Promotion review {review_id} not found after insert.")
    return review


def fetch_promotion_review_by_id(
    conn: sqlite3.Connection,
    *,
    review_id: int,
) -> PromotionReviewRecord | None:
    row = conn.execute(
        "SELECT * FROM promotion_reviews WHERE id = ?",
        (review_id,),
    ).fetchone()
    return None if row is None else _map_review_row(row)


def fetch_open_promotion_review(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    strategy_name: str,
) -> PromotionReviewRecord | None:
    row = conn.execute(
        """
        SELECT *
        FROM promotion_reviews
        WHERE account_id = ? AND strategy_name = ? AND review_state = ?
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (account_id, strategy_name, PROMOTION_REVIEW_STATE_REQUESTED),
    ).fetchone()
    return None if row is None else _map_review_row(row)


def fetch_promotion_reviews_for_account(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    strategy_name: str | None = None,
    limit: int,
) -> list[PromotionReviewRecord]:
    if strategy_name is None:
        rows = conn.execute(
            """
            SELECT *
            FROM promotion_reviews
            WHERE account_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (account_id, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT *
            FROM promotion_reviews
            WHERE account_id = ? AND strategy_name = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (account_id, strategy_name, limit),
        ).fetchall()
    return [_map_review_row(row) for row in rows]


def insert_promotion_review_event(
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
) -> PromotionReviewEvent:
    next_seq_row = conn.execute(
        "SELECT COALESCE(MAX(event_seq), 0) + 1 AS next_seq FROM promotion_review_events WHERE review_id = ?",
        (review_id,),
    ).fetchone()
    if next_seq_row is None:
        raise ValueError(f"Unable to compute next event sequence for review {review_id}.")
    event_seq = int(next_seq_row["next_seq"])
    cursor = conn.execute(
        """
        INSERT INTO promotion_review_events (
            review_id,
            event_seq,
            event_type,
            actor_type,
            actor_name,
            from_review_state,
            to_review_state,
            note,
            event_payload,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            review_id,
            event_seq,
            event_type,
            PROMOTION_REVIEW_ACTOR_TYPE_OPERATOR,
            actor_name,
            from_review_state,
            to_review_state,
            note,
            json.dumps(event_payload, separators=(",", ":"), sort_keys=True),
            created_at,
        ),
    )
    event_id = cursor.lastrowid
    if not isinstance(event_id, int):
        raise ValueError("Expected integer promotion review event id after insert.")
    row = conn.execute(
        "SELECT * FROM promotion_review_events WHERE id = ?",
        (event_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"Promotion review event {event_id} not found after insert.")
    return _map_event_row(row)


def fetch_promotion_review_events(
    conn: sqlite3.Connection,
    *,
    review_id: int,
) -> list[PromotionReviewEvent]:
    rows = conn.execute(
        """
        SELECT *
        FROM promotion_review_events
        WHERE review_id = ?
        ORDER BY event_seq ASC, id ASC
        """,
        (review_id,),
    ).fetchall()
    return [_map_event_row(row) for row in rows]


def update_promotion_review_record(
    conn: sqlite3.Connection,
    *,
    review_id: int,
    review_state: str,
    reviewed_by: str | None,
    operator_summary_note: str | None,
    updated_at: str,
    closed_at: str | None,
) -> PromotionReviewRecord:
    conn.execute(
        """
        UPDATE promotion_reviews
        SET review_state = ?, reviewed_by = ?, operator_summary_note = ?, updated_at = ?, closed_at = ?
        WHERE id = ?
        """,
        (
            review_state,
            reviewed_by,
            operator_summary_note or "",
            updated_at,
            closed_at,
            review_id,
        ),
    )
    review = fetch_promotion_review_by_id(conn, review_id=review_id)
    if review is None:
        raise ValueError(f"Promotion review {review_id} not found after update.")
    return review
