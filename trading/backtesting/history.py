from __future__ import annotations

import sqlite3

from trading.coercion import coerce_float


def _safe_return_pct(starting_equity: object, ending_equity: object) -> float | None:
    start = coerce_float(starting_equity)
    end = coerce_float(ending_equity)
    if start is None or end is None:
        return None
    if start <= 0:
        return None
    return ((end / start) - 1.0) * 100.0


def load_strategy_backtest_returns(
    conn: sqlite3.Connection,
    account_id: int,
    strategy_names: list[str],
    start_day: str,
    end_day: str,
) -> list[tuple[str, float]]:
    """Load per-run strategy returns from backtest history within a date window."""
    if not strategy_names:
        return []

    placeholders = ",".join(["?"] * len(strategy_names))
    rows = conn.execute(
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

    returns: list[tuple[str, float]] = []
    for row in rows:
        strategy_name = str(row["strategy_name"] or "").strip()
        if not strategy_name:
            continue

        ret = _safe_return_pct(row["starting_equity"], row["ending_equity"])
        if ret is None:
            continue

        returns.append((strategy_name, ret))

    return returns
