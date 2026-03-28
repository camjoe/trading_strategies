from __future__ import annotations

import sqlite3


def update_account_rotation_state(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    strategy: str,
    rotation_active_index: int,
    rotation_active_strategy: str,
    rotation_last_at: str,
) -> None:
    conn.execute(
        """
        UPDATE accounts
        SET strategy = ?,
            rotation_active_index = ?,
            rotation_active_strategy = ?,
            rotation_last_at = ?
        WHERE id = ?
        """,
        (
            strategy,
            rotation_active_index,
            rotation_active_strategy,
            rotation_last_at,
            account_id,
        ),
    )
    conn.commit()
