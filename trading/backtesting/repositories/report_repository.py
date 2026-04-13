from __future__ import annotations

import sqlite3


def fetch_recent_backtest_runs(conn: sqlite3.Connection, *, limit: int) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT r.id, r.run_name, r.start_date, r.end_date, r.created_at, r.slippage_bps, r.fee_per_trade,
               r.tickers_file, a.name AS account_name, a.strategy
        FROM backtest_runs r
        JOIN accounts a ON a.id = r.account_id
        ORDER BY r.id DESC
        LIMIT ?
        """,
        (int(limit),),
    ).fetchall()


def fetch_latest_backtest_run_for_account(conn: sqlite3.Connection, *, account_name: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT r.id, r.run_name, r.start_date, r.end_date, r.created_at, r.slippage_bps, r.fee_per_trade,
               r.tickers_file, a.name AS account_name, a.strategy
        FROM backtest_runs r
        JOIN accounts a ON a.id = r.account_id
        WHERE a.name = ?
        ORDER BY r.id DESC
        LIMIT 1
        """,
        (account_name,),
    ).fetchone()


def fetch_latest_backtest_run_id_for_account(conn: sqlite3.Connection, *, account_name: str) -> int | None:
    row = conn.execute(
        """
        SELECT r.id
        FROM backtest_runs r
        JOIN accounts a ON a.id = r.account_id
        WHERE a.name = ?
        ORDER BY r.id DESC
        LIMIT 1
        """,
        (account_name,),
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
        WHERE r.account_id = ?
          AND LOWER(COALESCE(r.strategy_name, a.strategy)) = LOWER(?)
        ORDER BY r.created_at DESC, r.id DESC
        LIMIT 1
        """,
        (int(account_id), strategy_name),
    ).fetchone()
    if row is None:
        return None
    return int(row["id"])


def fetch_backtest_report_run(conn: sqlite3.Connection, run_id: int) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT r.id, r.run_name, r.start_date, r.end_date, r.created_at, r.slippage_bps, r.fee_per_trade,
             r.tickers_file, r.notes, r.warnings, a.name AS account_name,
             COALESCE(r.strategy_name, a.strategy) AS strategy,
             a.benchmark_ticker,
             a.initial_cash
        FROM backtest_runs r
        JOIN accounts a ON a.id = r.account_id
        WHERE r.id = ?
        """,
        (run_id,),
    ).fetchone()


def fetch_backtest_report_snapshots(conn: sqlite3.Connection, run_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT snapshot_time, cash, market_value, equity, realized_pnl, unrealized_pnl
        FROM backtest_equity_snapshots
        WHERE run_id = ?
        ORDER BY snapshot_time ASC
        """,
        (run_id,),
    ).fetchall()


def fetch_backtest_report_trades(conn: sqlite3.Connection, run_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT trade_time, ticker, side, qty, price, fee
        FROM backtest_trades
        WHERE run_id = ?
        ORDER BY trade_time, id
        """,
        (run_id,),
    ).fetchall()
