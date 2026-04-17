from __future__ import annotations

import sqlite3


def fetch_global_settings_row(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT runtime_max_trades_per_day, runtime_max_trades_per_minute, updated_at
        FROM global_settings
        WHERE id = 1
        """
    ).fetchone()


def upsert_runtime_throttle_settings(
    conn: sqlite3.Connection,
    *,
    runtime_max_trades_per_day: int | None,
    runtime_max_trades_per_minute: int | None,
    updated_at: str,
) -> None:
    conn.execute(
        """
        INSERT INTO global_settings (
            id,
            runtime_max_trades_per_day,
            runtime_max_trades_per_minute,
            updated_at
        )
        VALUES (1, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            runtime_max_trades_per_day = excluded.runtime_max_trades_per_day,
            runtime_max_trades_per_minute = excluded.runtime_max_trades_per_minute,
            updated_at = excluded.updated_at
        """,
        (
            runtime_max_trades_per_day,
            runtime_max_trades_per_minute,
            updated_at,
        ),
    )
    conn.commit()
