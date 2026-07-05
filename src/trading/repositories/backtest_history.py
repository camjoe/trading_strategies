from __future__ import annotations

import sqlite3


class BacktestRunRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def fetch_by_strategy_window(
        self,
        *,
        account_id: int,
        strategy_names: list[str],
        start_day: str,
        end_day: str,
    ) -> list[sqlite3.Row]:
        # Strategy is a strategies FK (P3); match/return the canonical catalog key,
        # which is what rotation schedules carry. `st` aliases the strategies join;
        # `eq` aliases the equity-snapshot subqueries.
        placeholders = ",".join(["?"] * len(strategy_names))
        return self._conn.execute(
            f"""
            SELECT
                st.strategy_key AS strategy_name,
                (
                    SELECT eq.equity
                    FROM backtest_equity_snapshots eq
                    WHERE eq.run_id = r.id
                    ORDER BY eq.snapshot_time ASC, eq.id ASC
                    LIMIT 1
                ) AS starting_equity,
                (
                    SELECT eq.equity
                    FROM backtest_equity_snapshots eq
                    WHERE eq.run_id = r.id
                    ORDER BY eq.snapshot_time DESC, eq.id DESC
                    LIMIT 1
                ) AS ending_equity
            FROM backtest_runs r
            JOIN strategies st ON st.id = r.strategy_id
            WHERE r.account_id = ?
              AND st.strategy_key IN ({placeholders})
              AND r.end_date >= ?
              AND r.end_date <= ?
            ORDER BY r.end_date DESC, r.id DESC
            """,
            (account_id, *strategy_names, start_day, end_day),
        ).fetchall()
