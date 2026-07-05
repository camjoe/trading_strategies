"""Seed module for backtest run data used in the shared seeded_conn fixture."""

from __future__ import annotations

import sqlite3

from tests.support.seed.accounts import ACCT_TREND, PROMOTION_STRATEGY, seed_account_id
from tests.support.strategies import strategy_id_for

BACKTEST_RUN_NAME = "seed_run_a"


def seed_backtest_run(conn: sqlite3.Connection) -> None:
    acct_id = seed_account_id(conn, ACCT_TREND)
    conn.execute(
        """
        INSERT INTO backtest_runs
            (account_id, strategy_id, run_name, start_date, end_date, created_at,
             slippage_bps, fee_per_trade, tickers_file)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            acct_id,
            strategy_id_for(conn, PROMOTION_STRATEGY),
            BACKTEST_RUN_NAME,
            "2025-07-01",
            "2025-12-31",
            "2026-01-01T00:00:00Z",
            5.0,
            0.0,
            "src/infrastructure/config/trade_universe.txt",
        ),
    )


__all__ = [
    "BACKTEST_RUN_NAME",
    "seed_backtest_run",
]
