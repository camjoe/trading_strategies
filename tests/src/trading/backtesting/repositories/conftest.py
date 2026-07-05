from __future__ import annotations

import sqlite3
from collections.abc import Callable

import pytest

from trading.services.accounts import create_account

from tests.support.strategies import strategy_id_for


@pytest.fixture
def bt_repo_account(conn: sqlite3.Connection) -> tuple[str, int]:
    """Standard repository test account; returns (account_name, account_id)."""
    create_account(conn, "acct_bt_repo", "trend_v1", 10_000.0, "SPY")
    account_id = int(conn.execute("SELECT id FROM accounts WHERE name = ?", ("acct_bt_repo",)).fetchone()["id"])
    return "acct_bt_repo", account_id


@pytest.fixture
def seed_bt_run(conn: sqlite3.Connection) -> Callable[..., int]:
    """Factory that inserts a minimal backtest run with two equity snapshots."""

    def _seed(
        account_id: int,
        *,
        strategy_name: str = "trend_v1",
        run_name: str = "repo-test-run",
        created_at: str = "2026-02-01T00:00:00Z",
        start_equity: float = 1_000.0,
        end_equity: float = 1_100.0,
        end_date: str = "2026-01-31",
    ) -> int:
        run_id = int(
            conn.execute(
                """
                INSERT INTO backtest_runs (
                    account_id, strategy_id, run_name, start_date, end_date,
                    created_at, slippage_bps, fee_per_trade, tickers_file, notes, warnings
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    account_id,
                    strategy_id_for(conn, strategy_name),
                    run_name,
                    "2026-01-01",
                    end_date,
                    created_at,
                    0.0,
                    0.0,
                    "src/infrastructure/config/trade_universe.txt",
                    "",
                    "",
                ),
            ).lastrowid
        )
        conn.executemany(
            """
            INSERT INTO backtest_equity_snapshots (
                run_id, snapshot_time, cash, market_value, equity, realized_pnl, unrealized_pnl
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (run_id, "2026-01-01T00:00:00Z", start_equity, 0.0, start_equity, 0.0, 0.0),
                (run_id, f"{end_date}T00:00:00Z", end_equity, 0.0, end_equity, 0.0, 0.0),
            ],
        )
        conn.commit()
        return run_id

    return _seed
