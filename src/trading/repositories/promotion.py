from __future__ import annotations

import json
import sqlite3

from trading.models.evaluation import StrategyEvaluationArtifact
from trading.models.promotion import (
    PROMOTION_REVIEW_ACTOR_TYPE_OPERATOR,
    PromotionAssessment,
    PromotionReviewEvent,
    PromotionReviewEventType,
    PromotionReviewRecord,
    PromotionReviewState,
    PromotionStage,
    PromotionStatus,
)

# Compact JSON storage keeps persisted review payloads stable and easy to diff.
JSON_COMPACT_SEPARATORS = (",", ":")


def _row_text(row: sqlite3.Row, key: str) -> str | None:
    value = row[key]
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _opt_review_state(value: str | None) -> PromotionReviewState | None:
    return None if value is None else PromotionReviewState(value)


def _row_json_object(row: sqlite3.Row, key: str) -> dict[str, object]:
    raw = row[key]
    if raw is None:
        return {}
    payload = json.loads(str(raw))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in column '{key}'.")
    return payload


def _json_object_dumps(payload: dict[str, object]) -> str:
    return json.dumps(payload, separators=JSON_COMPACT_SEPARATORS, sort_keys=True)


def _db_optional_text(value: str | None) -> str:
    return value or ""


class PromotionReviewRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    @staticmethod
    def _map_review_row(row: sqlite3.Row) -> PromotionReviewRecord:
        return PromotionReviewRecord(
            id=int(row["id"]),
            account_id=int(row["account_id"]),
            account_name_snapshot=str(row["account_name_snapshot"]),
            strategy_name=str(row["strategy_name"]),
            review_state=PromotionReviewState(str(row["review_state"])),
            assessment_stage=PromotionStage(str(row["assessment_stage"])),
            assessment_status=PromotionStatus(str(row["assessment_status"])),
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

    @staticmethod
    def _map_event_row(row: sqlite3.Row) -> PromotionReviewEvent:
        return PromotionReviewEvent(
            id=int(row["id"]),
            review_id=int(row["review_id"]),
            event_seq=int(row["event_seq"]),
            event_type=PromotionReviewEventType(str(row["event_type"])),
            actor_type=str(row["actor_type"]),
            actor_name=_row_text(row, "actor_name"),
            from_review_state=_opt_review_state(_row_text(row, "from_review_state")),
            to_review_state=_opt_review_state(_row_text(row, "to_review_state")),
            note=_row_text(row, "note"),
            event_payload=_row_json_object(row, "event_payload"),
            created_at=str(row["created_at"]),
        )

    def _require_review(self, *, review_id: int, context: str) -> PromotionReviewRecord:
        review = self.fetch_by_id(review_id=review_id)
        if review is None:
            raise ValueError(f"Promotion review {review_id} not found after {context}.")
        return review

    def _require_event(self, *, event_id: int) -> PromotionReviewEvent:
        row = self._conn.execute(
            "SELECT * FROM promotion_review_events WHERE id = ?",
            (event_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"Promotion review event {event_id} not found after insert.")
        return self._map_event_row(row)

    def insert_review(
        self,
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

        cursor = self._conn.execute(
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
                PromotionReviewState.REQUESTED,
                assessment.stage,
                assessment.status,
                int(assessment.ready_for_live),
                assessment.overall_confidence,
                int(assessment.live_trading_enabled),
                assessment.version,
                evaluation.meta.artifact_version,
                _json_object_dumps(assessment.to_payload()),
                _json_object_dumps(evaluation.to_payload()),
                requested_by,
                None,
                _db_optional_text(operator_summary_note),
                created_at,
                created_at,
                None,
            ),
        )
        review_id = cursor.lastrowid
        if not isinstance(review_id, int):
            raise ValueError("Expected integer promotion review id after insert.")
        return self._require_review(review_id=review_id, context="insert")

    def fetch_by_id(self, *, review_id: int) -> PromotionReviewRecord | None:
        row = self._conn.execute(
            "SELECT * FROM promotion_reviews WHERE id = ?",
            (review_id,),
        ).fetchone()
        return None if row is None else self._map_review_row(row)

    def fetch_open(
        self,
        *,
        account_id: int,
        strategy_name: str,
    ) -> PromotionReviewRecord | None:
        row = self._conn.execute(
            """
            SELECT *
            FROM promotion_reviews
            WHERE account_id = ? AND strategy_name = ? AND review_state = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (account_id, strategy_name, PromotionReviewState.REQUESTED),
        ).fetchone()
        return None if row is None else self._map_review_row(row)

    def fetch_for_account(
        self,
        *,
        account_id: int,
        strategy_name: str | None = None,
        limit: int,
    ) -> list[PromotionReviewRecord]:
        query = [
            "SELECT *",
            "FROM promotion_reviews",
            "WHERE account_id = ?",
        ]
        params: tuple[object, ...] = (account_id,)
        if strategy_name is not None:
            query.append("AND strategy_name = ?")
            params += (strategy_name,)
        query.extend(["ORDER BY created_at DESC, id DESC", "LIMIT ?"])
        rows = self._conn.execute("\n".join(query), params + (limit,)).fetchall()
        return [self._map_review_row(row) for row in rows]

    def insert_event(
        self,
        *,
        review_id: int,
        event_type: PromotionReviewEventType,
        actor_name: str | None,
        from_review_state: PromotionReviewState | None,
        to_review_state: PromotionReviewState | None,
        note: str | None,
        event_payload: dict[str, object],
        created_at: str,
    ) -> PromotionReviewEvent:
        next_seq_row = self._conn.execute(
            "SELECT COALESCE(MAX(event_seq), 0) + 1 AS next_seq FROM promotion_review_events WHERE review_id = ?",
            (review_id,),
        ).fetchone()
        if next_seq_row is None:
            raise ValueError(f"Unable to compute next event sequence for review {review_id}.")
        event_seq = int(next_seq_row["next_seq"])
        cursor = self._conn.execute(
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
                _json_object_dumps(event_payload),
                created_at,
            ),
        )
        event_id = cursor.lastrowid
        if not isinstance(event_id, int):
            raise ValueError("Expected integer promotion review event id after insert.")
        return self._require_event(event_id=event_id)

    def fetch_events(self, *, review_id: int) -> list[PromotionReviewEvent]:
        rows = self._conn.execute(
            """
            SELECT *
            FROM promotion_review_events
            WHERE review_id = ?
            ORDER BY event_seq ASC, id ASC
            """,
            (review_id,),
        ).fetchall()
        return [self._map_event_row(row) for row in rows]

    def update_review(
        self,
        *,
        review_id: int,
        review_state: PromotionReviewState,
        reviewed_by: str | None,
        operator_summary_note: str | None,
        updated_at: str,
        closed_at: str | None,
    ) -> PromotionReviewRecord:
        self._conn.execute(
            """
            UPDATE promotion_reviews
            SET review_state = ?, reviewed_by = ?, operator_summary_note = ?, updated_at = ?, closed_at = ?
            WHERE id = ?
            """,
            (
                review_state,
                reviewed_by,
                _db_optional_text(operator_summary_note),
                updated_at,
                closed_at,
                review_id,
            ),
        )
        return self._require_review(review_id=review_id, context="update")
