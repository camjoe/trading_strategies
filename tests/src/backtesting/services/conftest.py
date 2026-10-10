from __future__ import annotations

import sqlite3
from collections.abc import Callable

import pytest

from tests.support.strategies import ensure_strategy_id_for_label


@pytest.fixture
def seed_history_run(conn: sqlite3.Connection) -> Callable[..., None]:
    """Insert a backtest run with two equity snapshots for history-service tests."""

    def _seed(
        account_id: int,
        *,
        strategy_name: str,
        end_date: str,
        start_equity: float,
        end_equity: float,
    ) -> None:
        conn.execute(
            """
            INSERT INTO backtest_runs (
                account_id, strategy_id, run_name, start_date, end_date,
                slippage_bps, fee_per_trade, warnings, created_at
            )
            VALUES (?, ?, 'test', '2026-01-01', ?, 0.0, 0.0, '[]', '2026-03-01T00:00:00Z')
            """,
            (account_id, ensure_strategy_id_for_label(conn, strategy_name), end_date),
        )
        run_id = int(conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"])
        conn.executemany(
            """
            INSERT INTO backtest_equity_snapshots (
                run_id, snapshot_date, cash, market_value, equity, realized_pnl, unrealized_pnl
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (run_id, "2026-03-01T00:00:00Z", 0.0, 0.0, start_equity, 0.0, 0.0),
                (run_id, "2026-03-02T00:00:00Z", 0.0, 0.0, end_equity, 0.0, 0.0),
            ],
        )
        conn.commit()

    return _seed
