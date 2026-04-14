from __future__ import annotations

import sqlite3

from common.coercion import row_expect_int, row_expect_str
from common.time import utc_now_iso


def _fetch_backtest_run_scope(conn: sqlite3.Connection, *, run_id: int) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT r.account_id, COALESCE(r.strategy_name, a.strategy) AS strategy_name
        FROM backtest_runs r
        JOIN accounts a ON a.id = r.account_id
        WHERE r.id = ?
        """,
        (int(run_id),),
    ).fetchone()


def insert_walk_forward_group(
    conn: sqlite3.Connection,
    *,
    primary_run_id: int,
    grouping_key: str,
    run_name_prefix: str | None,
    start_date: str,
    end_date: str,
    test_months: int,
    step_months: int,
    window_count: int,
    average_return_pct: float,
    median_return_pct: float,
    best_return_pct: float,
    worst_return_pct: float,
    created_at: str | None = None,
) -> int:
    run_scope = _fetch_backtest_run_scope(conn, run_id=primary_run_id)
    if run_scope is None:
        raise ValueError(f"Backtest run {primary_run_id} not found.")

    cursor = conn.execute(
        """
        INSERT INTO walk_forward_groups (
            grouping_key,
            account_id,
            strategy_name,
            run_name_prefix,
            start_date,
            end_date,
            test_months,
            step_months,
            window_count,
            average_return_pct,
            median_return_pct,
            best_return_pct,
            worst_return_pct,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            grouping_key,
            row_expect_int(run_scope, "account_id"),
            row_expect_str(run_scope, "strategy_name"),
            run_name_prefix,
            start_date,
            end_date,
            int(test_months),
            int(step_months),
            int(window_count),
            float(average_return_pct),
            float(median_return_pct),
            float(best_return_pct),
            float(worst_return_pct),
            created_at or utc_now_iso(),
        ),
    )
    assert cursor.lastrowid is not None
    return int(cursor.lastrowid)


def insert_walk_forward_group_run(
    conn: sqlite3.Connection,
    *,
    group_id: int,
    run_id: int,
    window_index: int,
    window_start: str,
    window_end: str,
    total_return_pct: float,
) -> None:
    conn.execute(
        """
        INSERT INTO walk_forward_group_runs (
            group_id,
            run_id,
            window_index,
            window_start,
            window_end,
            total_return_pct
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            int(group_id),
            int(run_id),
            int(window_index),
            window_start,
            window_end,
            float(total_return_pct),
        ),
    )


def fetch_latest_walk_forward_group_for_account_strategy(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    strategy_name: str,
) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT id,
               grouping_key,
               account_id,
               strategy_name,
               run_name_prefix,
               start_date,
               end_date,
               test_months,
               step_months,
               window_count,
               average_return_pct,
               median_return_pct,
               best_return_pct,
               worst_return_pct,
               created_at
        FROM walk_forward_groups
        WHERE account_id = ?
          AND LOWER(strategy_name) = LOWER(?)
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (int(account_id), strategy_name),
    ).fetchone()


def fetch_latest_walk_forward_group_for_account(
    conn: sqlite3.Connection,
    *,
    account_id: int,
) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT id,
               grouping_key,
               account_id,
               strategy_name,
               run_name_prefix,
               start_date,
               end_date,
               test_months,
               step_months,
               window_count,
               average_return_pct,
               median_return_pct,
               best_return_pct,
               worst_return_pct,
               created_at
        FROM walk_forward_groups
        WHERE account_id = ?
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (int(account_id),),
    ).fetchone()


def fetch_walk_forward_group_by_id(
    conn: sqlite3.Connection,
    *,
    group_id: int,
) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT id,
               grouping_key,
               account_id,
               strategy_name,
               run_name_prefix,
               start_date,
               end_date,
               test_months,
               step_months,
               window_count,
               average_return_pct,
               median_return_pct,
               best_return_pct,
               worst_return_pct,
               created_at
        FROM walk_forward_groups
        WHERE id = ?
        """,
        (int(group_id),),
    ).fetchone()


def fetch_walk_forward_group_runs(
    conn: sqlite3.Connection,
    *,
    group_id: int,
) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT run_id, window_index, window_start, window_end, total_return_pct
        FROM walk_forward_group_runs
        WHERE group_id = ?
        ORDER BY window_index ASC, id ASC
        """,
        (int(group_id),),
    ).fetchall()
