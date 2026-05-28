from __future__ import annotations

import sqlite3


def fetch_strategy_backtest_rows(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    strategy_names: list[str],
    start_day: str,
    end_day: str,
) -> list[sqlite3.Row]:
    placeholders = ",".join(["?"] * len(strategy_names))
    return conn.execute(
        f"""
        SELECT
            r.strategy_name,
            (
                SELECT s.equity
                FROM backtest_equity_snapshots s
                WHERE s.run_id = r.id
                ORDER BY s.snapshot_time ASC, s.id ASC
                LIMIT 1
            ) AS starting_equity,
            (
                SELECT s.equity
                FROM backtest_equity_snapshots s
                WHERE s.run_id = r.id
                ORDER BY s.snapshot_time DESC, s.id DESC
                LIMIT 1
            ) AS ending_equity
        FROM backtest_runs r
        WHERE r.account_id = ?
          AND r.strategy_name IN ({placeholders})
          AND r.end_date >= ?
          AND r.end_date <= ?
        ORDER BY r.end_date DESC, r.id DESC
        """,
        (account_id, *strategy_names, start_day, end_day),
    ).fetchall()
