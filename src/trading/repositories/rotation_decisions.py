from __future__ import annotations

import datetime as dt
import sqlite3


class RotationDecisionRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def insert(
        self,
        *,
        sleeve_id: int,
        decision_time: str,
        incumbent_strategy: str | None,
        challenger_strategy: str | None,
        selected_strategy: str | None,
        rotation_action: str,
        cooldown_active: int,
        score_components_json: str,
        gate_results_json: str,
        decision_reason: str | None,
        config_version: str | None,
        param_set_id: int | None,
        created_at: str,
    ) -> int:
        cursor = self._conn.execute(
            """
            INSERT INTO rotation_decisions (
                sleeve_id,
                decision_time,
                incumbent_strategy,
                challenger_strategy,
                selected_strategy,
                rotation_action,
                cooldown_active,
                score_components_json,
                gate_results_json,
                decision_reason,
                config_version,
                param_set_id,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(sleeve_id),
                decision_time,
                incumbent_strategy,
                challenger_strategy,
                selected_strategy,
                rotation_action,
                int(cooldown_active),
                score_components_json,
                gate_results_json,
                decision_reason,
                config_version,
                None if param_set_id is None else int(param_set_id),
                created_at,
            ),
        )
        self._conn.commit()
        if cursor.lastrowid is None:
            raise ValueError("Expected rotation_decisions id after insert.")
        return int(cursor.lastrowid)

    def fetch_latest(self, *, sleeve_id: int) -> sqlite3.Row | None:
        return self._conn.execute(
            """
            SELECT *
            FROM rotation_decisions
            WHERE sleeve_id = ?
            ORDER BY decision_time DESC, id DESC
            LIMIT 1
            """,
            (int(sleeve_id),),
        ).fetchone()

    def fetch_for_sleeve(self, *, sleeve_id: int, limit: int) -> list[sqlite3.Row]:
        return self._conn.execute(
            """
            SELECT *
            FROM rotation_decisions
            WHERE sleeve_id = ?
            ORDER BY decision_time DESC, id DESC
            LIMIT ?
            """,
            (int(sleeve_id), int(limit)),
        ).fetchall()

    def fetch_for_sleeve_on_date(self, *, sleeve_id: int, report_date: str) -> list[sqlite3.Row]:
        next_date = (dt.date.fromisoformat(report_date) + dt.timedelta(days=1)).isoformat()
        return self._conn.execute(
            """
            SELECT *
            FROM rotation_decisions
            WHERE sleeve_id = ?
              AND decision_time >= ?
              AND decision_time < ?
            ORDER BY decision_time ASC, id ASC
            """,
            (int(sleeve_id), report_date, next_date),
        ).fetchall()

    def fetch_latest_rotate_action(self, *, sleeve_id: int) -> sqlite3.Row | None:
        """Return the most recent decision where rotation_action = 'rotate'."""
        return self._conn.execute(
            """
            SELECT *
            FROM rotation_decisions
            WHERE sleeve_id = ?
              AND rotation_action = 'rotate'
            ORDER BY decision_time DESC, id DESC
            LIMIT 1
            """,
            (int(sleeve_id),),
        ).fetchone()
