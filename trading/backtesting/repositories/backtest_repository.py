from __future__ import annotations

import sqlite3
from datetime import date

from common.time import utc_now_iso
from trading.backtesting.models import BacktestConfig


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
    cursor = conn.execute(
        """
        INSERT INTO backtest_runs (
            account_id,
            strategy_name,
            run_name,
            start_date,
            end_date,
            created_at,
            slippage_bps,
            fee_per_trade,
            tickers_file,
            notes,
            warnings
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            account_id,
            strategy_name,
            cfg.run_name,
            start_date.isoformat(),
            end_date.isoformat(),
            utc_now_iso(),
            float(cfg.slippage_bps),
            float(cfg.fee_per_trade),
            cfg.tickers_file,
            "First working backtest version: deterministic daily-bar simulator.",
            " | ".join(warnings),
        ),
    )
    conn.commit()
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
        INSERT INTO backtest_trades (
            run_id, trade_time, ticker, side, qty, price, fee, slippage_bps, note
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (run_id, trade_time, ticker, side, qty, price, fee, slippage_bps, note),
    )


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
            run_id, snapshot_time, cash, market_value, equity, realized_pnl, unrealized_pnl
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (run_id, snapshot_time, cash, market_value, equity, realized_pnl, unrealized_pnl),
    )
