"""Persistence operations for generated fixture databases (demo and sandbox).

Down to one record: a promotion review. ``PromotionReviewRepository.insert_review``
builds its row from real ``PromotionAssessment`` and ``StrategyEvaluationArtifact``
objects, which a fixture has no way to produce, so this writes the stub payloads
directly. Give the fixture a way to build those artifacts and this module goes
with it.

Everything else the seeder needs goes through the repository or service that
owns it — see ``trading.services.fixtures.seeding``.
"""

from __future__ import annotations

import sqlite3

from trading.persistence.json_columns import dumps_json_column
from trading.persistence.unit_of_work import commit_unit_of_work

# Assessment/evaluation artifact versions on seeded promotion reviews. The
# `fixture-` prefix keeps them sortable alongside real versions while remaining
# obviously synthetic.
FIXTURE_ARTIFACT_VERSION = "fixture-v1"


class FixtureSeedRepository:
    """Write coherent synthetic records through one repository boundary."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert_promotion_review(self, *, account_id: int, account_name: str, strategy_key: str, now_iso: str) -> None:
        strategy = self._conn.execute("SELECT id FROM strategies WHERE strategy_key = ?", (strategy_key,)).fetchone()
        if strategy is None:
            raise ValueError(f"Fixture strategy '{strategy_key}' is missing.")
        assessment = {"sample": True, "label": "Synthetic fixture evidence", "status": "ready_for_review"}
        evaluation = {"sample": True, "label": "Synthetic fixture evidence", "trade_count": 15, "snapshot_count": 30}
        cursor = self._conn.execute(
            """INSERT INTO promotion_reviews
               (account_id, account_name_snapshot, strategy_name, review_state, assessment_stage,
                assessment_status, ready_for_live, overall_confidence, live_trading_enabled_snapshot,
                promotion_assessment_version, evaluation_artifact_version, frozen_assessment_payload,
                frozen_evaluation_payload, requested_by, operator_summary_note, created_at, updated_at, strategy_id)
               VALUES (?, ?, ?, 'requested', 'promotion_review', 'ready_for_review', 0, 0.82, 0,
                       ?, ?, ?, ?, 'generated-fixture',
                       'Synthetic sample evidence only; not suitable for live-trading decisions.', ?, ?, ?)""",
            (
                account_id,
                account_name,
                strategy_key,
                FIXTURE_ARTIFACT_VERSION,
                FIXTURE_ARTIFACT_VERSION,
                dumps_json_column(assessment),
                dumps_json_column(evaluation),
                now_iso,
                now_iso,
                int(strategy["id"]),
            ),
        )
        review_id = cursor.lastrowid
        if review_id is None:
            raise ValueError("Expected a review id after inserting the fixture promotion review.")
        # A review with no events is an unreachable state in the real workflow:
        # the request that creates it is itself the first recorded transition.
        self._conn.execute(
            """INSERT INTO promotion_review_events
               (review_id, event_seq, event_type, actor_type, actor_name, from_review_state,
                to_review_state, note, created_at)
               VALUES (?, 1, 'requested', 'operator', 'generated-fixture', NULL, 'requested',
                       'Generated fixture review request.', ?)""",
            (review_id, now_iso),
        )
        commit_unit_of_work(self._conn)
