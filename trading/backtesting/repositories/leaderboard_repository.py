from __future__ import annotations

import sqlite3


def fetch_leaderboard_rows(
    conn: sqlite3.Connection,
    *,
    limit: int,
    account_name: str | None,
    strategy: str | None,
) -> list[sqlite3.Row]:
    query = """
        SELECT
            r.id AS run_id,
            r.run_name,
            r.start_date,
            r.end_date,
            r.created_at,
            a.name AS account_name,
            COALESCE(r.strategy_name, a.strategy) AS strategy,
            a.benchmark_ticker,
            a.initial_cash,
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
            ) AS ending_equity,
            (
                SELECT COUNT(*)
                FROM backtest_trades t
                WHERE t.run_id = r.id
            ) AS trade_count
        FROM backtest_runs r
        JOIN accounts a ON a.id = r.account_id
        WHERE (? IS NULL OR a.name = ?)
                    AND (? IS NULL OR LOWER(COALESCE(r.strategy_name, a.strategy)) LIKE '%' || LOWER(?) || '%')
        ORDER BY r.created_at DESC, r.id DESC
        LIMIT ?
    """
    return conn.execute(
        query,
        (account_name, account_name, strategy, strategy, int(limit)),
    ).fetchall()


def fetch_equity_rows(conn: sqlite3.Connection, run_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT equity
        FROM backtest_equity_snapshots
        WHERE run_id = ?
        ORDER BY snapshot_time ASC, id ASC
        """,
        (run_id,),
    ).fetchall()
