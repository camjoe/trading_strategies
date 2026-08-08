"""Leaderboard read queries.

Rows are converted to plain dicts before leaving the repository: ``sqlite3.Row``
is not a ``Mapping`` (no ``get``/``items``/``values``, and iterating it yields
values rather than keys), so handing one to a caller annotated for ``Mapping``
promises an interface it does not have. Conversion here matches the
``from_mapping(dict(row))`` boundary the other repositories already use.
"""

from __future__ import annotations

import sqlite3

from backtesting.models import BACKTEST_PURPOSE_STANDALONE


def fetch_leaderboard_rows(
    conn: sqlite3.Connection,
    *,
    limit: int,
    account_name: str | None,
    strategy: str | None,
) -> list[dict[str, object]]:
    query = """
        SELECT
            r.id AS run_id,
            r.run_name,
            r.start_date,
            r.end_date,
            r.created_at,
            a.name AS account_name,
            COALESCE(s.strategy_key, 'unknown') AS strategy,
            a.benchmark_ticker,
            a.initial_cash,
            (
                SELECT s.equity
                FROM backtest_equity_snapshots s
                WHERE s.run_id = r.id
                ORDER BY s.snapshot_date ASC, s.id ASC
                LIMIT 1
            ) AS starting_equity,
            (
                SELECT s.equity
                FROM backtest_equity_snapshots s
                WHERE s.run_id = r.id
                ORDER BY s.snapshot_date DESC, s.id DESC
                LIMIT 1
            ) AS ending_equity,
            (
                SELECT COUNT(*)
                FROM backtest_executions t
                WHERE t.run_id = r.id
            ) AS trade_count
        FROM backtest_runs r
        JOIN accounts a ON a.id = r.account_id
        LEFT JOIN strategies s ON s.id = r.strategy_id
        WHERE r.purpose = ?
                    AND (? IS NULL OR a.name = ?)
                    AND (? IS NULL OR LOWER(COALESCE(s.strategy_key, 'unknown')) LIKE '%' || LOWER(?) || '%')
        ORDER BY r.created_at DESC, r.id DESC
        LIMIT ?
    """
    rows = conn.execute(
        query,
        (BACKTEST_PURPOSE_STANDALONE, account_name, account_name, strategy, strategy, int(limit)),
    ).fetchall()
    return [dict(row) for row in rows]


def fetch_equity_rows(conn: sqlite3.Connection, run_id: int) -> list[dict[str, object]]:
    rows = conn.execute(
        """
        SELECT equity
        FROM backtest_equity_snapshots
        WHERE run_id = ?
        ORDER BY snapshot_date ASC, id ASC
        """,
        (run_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def fetch_trade_rows(conn: sqlite3.Connection, run_id: int) -> list[dict[str, object]]:
    rows = conn.execute(
        """
        SELECT ticker, side, qty, price, fee
        FROM backtest_executions
        WHERE run_id = ?
        ORDER BY execution_date ASC, id ASC
        """,
        (run_id,),
    ).fetchall()
    return [dict(row) for row in rows]
