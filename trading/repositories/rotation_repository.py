from __future__ import annotations

import sqlite3

from trading.database.db_common import in_placeholders


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


def fetch_open_rotation_episode(
    conn: sqlite3.Connection,
    *,
    account_id: int,
) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT *
        FROM rotation_episodes
        WHERE account_id = ?
          AND ended_at IS NULL
        ORDER BY started_at DESC, id DESC
        LIMIT 1
        """,
        (int(account_id),),
    ).fetchone()


def insert_rotation_episode(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    strategy_name: str,
    started_at: str,
    starting_equity: float,
    starting_realized_pnl: float,
) -> None:
    conn.execute(
        """
        INSERT INTO rotation_episodes (
            account_id,
            strategy_name,
            started_at,
            starting_equity,
            starting_realized_pnl
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            int(account_id),
            strategy_name,
            started_at,
            float(starting_equity),
            float(starting_realized_pnl),
        ),
    )
    conn.commit()


def close_rotation_episode(
    conn: sqlite3.Connection,
    *,
    episode_id: int,
    ended_at: str,
    ending_equity: float,
    ending_realized_pnl: float,
    realized_pnl_delta: float,
    snapshot_count: int,
) -> None:
    conn.execute(
        """
        UPDATE rotation_episodes
        SET ended_at = ?,
            ending_equity = ?,
            ending_realized_pnl = ?,
            realized_pnl_delta = ?,
            snapshot_count = ?
        WHERE id = ?
        """,
        (
            ended_at,
            float(ending_equity),
            float(ending_realized_pnl),
            float(realized_pnl_delta),
            int(snapshot_count),
            int(episode_id),
        ),
    )
    conn.commit()


def fetch_closed_rotation_episodes(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    strategy_names: list[str],
    start_iso: str,
    end_iso: str,
) -> list[sqlite3.Row]:
    if not strategy_names:
        return []
    placeholders = in_placeholders(strategy_names)
    return conn.execute(
        f"""
        SELECT *
        FROM rotation_episodes
        WHERE account_id = ?
          AND strategy_name IN ({placeholders})
          AND ended_at IS NOT NULL
          AND ended_at >= ?
          AND ended_at <= ?
        ORDER BY ended_at DESC, id DESC
        """,
        (int(account_id), *strategy_names, start_iso, end_iso),
    ).fetchall()


def fetch_latest_closed_rotation_episode(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    strategy_name: str,
) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT *
        FROM rotation_episodes
        WHERE account_id = ?
          AND strategy_name = ?
          AND ended_at IS NOT NULL
        ORDER BY ended_at DESC, id DESC
        LIMIT 1
        """,
        (int(account_id), strategy_name),
    ).fetchone()
