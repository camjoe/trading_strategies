from __future__ import annotations

import sqlite3


def insert_rotation_decision(
    conn: sqlite3.Connection,
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
    cursor = conn.execute(
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
    conn.commit()
    if cursor.lastrowid is None:
        raise ValueError("Expected rotation_decisions id after insert.")
    return int(cursor.lastrowid)


def fetch_latest_rotation_decision_for_sleeve(
    conn: sqlite3.Connection,
    *,
    sleeve_id: int,
) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT *
        FROM rotation_decisions
        WHERE sleeve_id = ?
        ORDER BY decision_time DESC, id DESC
        LIMIT 1
        """,
        (int(sleeve_id),),
    ).fetchone()


def fetch_rotation_decisions_for_sleeve(
    conn: sqlite3.Connection,
    *,
    sleeve_id: int,
    limit: int,
) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT *
        FROM rotation_decisions
        WHERE sleeve_id = ?
        ORDER BY decision_time DESC, id DESC
        LIMIT ?
        """,
        (int(sleeve_id), int(limit)),
    ).fetchall()
