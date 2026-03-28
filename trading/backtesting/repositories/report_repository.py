from __future__ import annotations

import sqlite3


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
