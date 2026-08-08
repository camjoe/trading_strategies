from __future__ import annotations

import sqlite3
from datetime import date

from common.time import utc_now_iso
from trading.backtesting.models import BacktestConfig
from trading.persistence.unit_of_work import commit_unit_of_work
from trading.repositories.book_bridge import strategy_id_for_label


def insert_backtest_run(
    conn: sqlite3.Connection,
    *,
    account_id: int,
    strategy_name: str,
    start_date: date,
    end_date: date,
    cfg: BacktestConfig,
    warnings: list[str],
) -> int:
    # The backtested strategy is a strategies FK. The caller
    # passes the canonical strategy key (resolved via resolve_strategy in the
    # service); the catalog row is seeded, so this is a lookup, not a create.
    created_at = utc_now_iso()
    strategy_id = strategy_id_for_label(conn, strategy_name, now_iso=created_at)
    cursor = conn.execute(
        """
        INSERT INTO backtest_runs (
            account_id,
            strategy_id,
            run_name,
            purpose,
            start_date,
            end_date,
            created_at,
            slippage_bps,
            fee_per_trade,
            tickers_file,
            notes,
            warnings
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            account_id,
            strategy_id,
            cfg.run_name,
            cfg.purpose,
            start_date.isoformat(),
            end_date.isoformat(),
            created_at,
            float(cfg.slippage_bps),
            float(cfg.fee_per_trade),
            cfg.tickers_file,
            "First working backtest version: deterministic daily-bar simulator.",
            " | ".join(warnings),
        ),
    )
    # Participates in the run's unit_of_work: commits standalone, defers inside a
    # scope so the header, executions, and snapshots land together or not at all.
    commit_unit_of_work(conn)
    assert cursor.lastrowid is not None
    return int(cursor.lastrowid)


def insert_backtest_trade(
    conn: sqlite3.Connection,
    *,
    run_id: int,
    trade_time: str,
    ticker: str,
    side: str,
    qty: float,
    price: float,
    fee: float,
    slippage_bps: float,
    note: str | None,
) -> None:
    conn.execute(
        """
        INSERT INTO backtest_executions (
            run_id, execution_date, ticker, side, qty, price, fee, slippage_bps, note
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (run_id, trade_time, ticker, side, qty, price, fee, slippage_bps, note),
    )
    commit_unit_of_work(conn)


def insert_backtest_snapshot(
    conn: sqlite3.Connection,
    *,
    run_id: int,
    snapshot_time: str,
    cash: float,
    market_value: float,
    equity: float,
    realized_pnl: float,
    unrealized_pnl: float,
) -> None:
    conn.execute(
        """
        INSERT INTO backtest_equity_snapshots (
            run_id, snapshot_date, cash, market_value, equity, realized_pnl, unrealized_pnl
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (run_id, snapshot_time, cash, market_value, equity, realized_pnl, unrealized_pnl),
    )
    commit_unit_of_work(conn)
