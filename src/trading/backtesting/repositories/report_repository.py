from __future__ import annotations

import sqlite3

from trading.backtesting.models import BACKTEST_PURPOSE_STANDALONE


def fetch_recent_backtest_runs(conn: sqlite3.Connection, *, limit: int) -> list[sqlite3.Row]:
    # Standalone-only: rolling-window (walk-forward) runs live in backtest_runs
    # too, but must not surface as generic recent backtests.
    return conn.execute(
        """
        SELECT r.id, r.run_name, r.start_date, r.end_date, r.created_at, r.slippage_bps, r.fee_per_trade,
               r.tickers_file, a.name AS account_name,
               COALESCE(s.strategy_key, 'unknown') AS strategy
        FROM backtest_runs r
        JOIN accounts a ON a.id = r.account_id
        LEFT JOIN strategies s ON s.id = r.strategy_id
        WHERE r.purpose = ?
        ORDER BY r.id DESC
        LIMIT ?
        """,
        (BACKTEST_PURPOSE_STANDALONE, int(limit)),
    ).fetchall()


def fetch_latest_backtest_run_for_account(conn: sqlite3.Connection, *, account_name: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT r.id, r.run_name, r.start_date, r.end_date, r.created_at, r.slippage_bps, r.fee_per_trade,
               r.tickers_file, a.name AS account_name,
               COALESCE(s.strategy_key, 'unknown') AS strategy
        FROM backtest_runs r
        JOIN accounts a ON a.id = r.account_id
        LEFT JOIN strategies s ON s.id = r.strategy_id
        WHERE a.name = ?
          AND r.purpose = ?
        ORDER BY r.id DESC
        LIMIT 1
        """,
        (account_name, BACKTEST_PURPOSE_STANDALONE),
    ).fetchone()


def fetch_latest_backtest_run_id_for_account(conn: sqlite3.Connection, *, account_name: str) -> int | None:
    row = conn.execute(
        """
        SELECT r.id
        FROM backtest_runs r
        JOIN accounts a ON a.id = r.account_id
        WHERE a.name = ?
          AND r.purpose = ?
        ORDER BY r.id DESC
        LIMIT 1
        """,
        (account_name, BACKTEST_PURPOSE_STANDALONE),
    ).fetchone()
    if row is None:
        return None
    return int(row["id"])


def fetch_latest_backtest_run_id_for_account_strategy(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    strategy_name: str,
) -> int | None:
    row = conn.execute(
        """
        SELECT r.id
        FROM backtest_runs r
        JOIN accounts a ON a.id = r.account_id
        LEFT JOIN strategies s ON s.id = r.strategy_id
        WHERE r.account_id = ?
          AND LOWER(s.strategy_key) = LOWER(?)
          AND r.purpose = ?
        ORDER BY r.created_at DESC, r.id DESC
        LIMIT 1
        """,
        (int(account_id), strategy_name, BACKTEST_PURPOSE_STANDALONE),
    ).fetchone()
    if row is None:
        return None
    return int(row["id"])


def fetch_backtest_report_run(conn: sqlite3.Connection, run_id: int) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT r.id, r.run_name, r.start_date, r.end_date, r.created_at, r.slippage_bps, r.fee_per_trade,
             r.tickers_file, r.notes, r.warnings, a.name AS account_name,
             COALESCE(s.strategy_key, 'unknown') AS strategy,
             a.benchmark_ticker,
             a.initial_cash
        FROM backtest_runs r
        JOIN accounts a ON a.id = r.account_id
        LEFT JOIN strategies s ON s.id = r.strategy_id
        WHERE r.id = ?
        """,
        (run_id,),
    ).fetchone()


def fetch_backtest_report_snapshots(conn: sqlite3.Connection, run_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT snapshot_date AS snapshot_time, cash, market_value, equity, realized_pnl, unrealized_pnl
        FROM backtest_equity_snapshots
        WHERE run_id = ?
        ORDER BY snapshot_date ASC
        """,
        (run_id,),
    ).fetchall()


def fetch_backtest_run_equity_bounds(conn: sqlite3.Connection, *, run_id: int) -> tuple[float, float] | None:
    """Return a run's ``(first_equity, last_equity)`` by snapshot date, or ``None``.

    The two equity marks needed to derive a run's total return without loading its
    whole equity curve. ``None`` when the run has no equity snapshots.
    """
    row = conn.execute(
        """
        SELECT
            (SELECT equity FROM backtest_equity_snapshots
             WHERE run_id = ? ORDER BY snapshot_date ASC, id ASC LIMIT 1) AS first_equity,
            (SELECT equity FROM backtest_equity_snapshots
             WHERE run_id = ? ORDER BY snapshot_date DESC, id DESC LIMIT 1) AS last_equity
        """,
        (int(run_id), int(run_id)),
    ).fetchone()
    if row is None or row["first_equity"] is None or row["last_equity"] is None:
        return None
    return (float(row["first_equity"]), float(row["last_equity"]))


def fetch_backtest_report_trades(conn: sqlite3.Connection, run_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT execution_date AS trade_time, ticker, side, qty, price, fee
        FROM backtest_executions
        WHERE run_id = ?
        ORDER BY execution_date, id
        """,
        (run_id,),
    ).fetchall()
