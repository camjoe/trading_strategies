from __future__ import annotations

import pytest
from fastapi import HTTPException

from common.time import utc_now_iso
from paper_trading_ui.backend.services import admin as services_admin


def test_delete_account_and_dependents_not_found_raises(conn) -> None:
    with pytest.raises(HTTPException) as exc_info:
        services_admin.delete_account_and_dependents("missing")
    assert exc_info.value.status_code == 404


def test_delete_account_and_dependents_removes_related_rows(conn, create_test_account) -> None:
    account_id = create_test_account("acct_delete")
    conn.execute(
        "INSERT INTO trades (account_id, ticker, side, qty, price, fee, trade_time) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (account_id, "AAPL", "buy", 1.0, 100.0, 0.0, "2026-01-02T00:00:00Z"),
    )
    conn.execute(
        """
        INSERT INTO equity_snapshots (account_id, snapshot_time, cash, market_value, equity, realized_pnl, unrealized_pnl)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (account_id, "2026-01-02T00:00:00Z", 900.0, 100.0, 1000.0, 0.0, 0.0),
    )
    conn.execute(
        """
        INSERT INTO backtest_runs (account_id, run_name, start_date, end_date, created_at, slippage_bps, fee_per_trade, tickers_file)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (account_id, "run-del", "2026-01-01", "2026-01-31", utc_now_iso(), 5.0, 0.0, "trading/config/trade_universe.txt"),
    )
    run = conn.execute("SELECT id FROM backtest_runs WHERE account_id = ?", (account_id,)).fetchone()
    assert run is not None
    run_id = int(run["id"])

    conn.execute(
        """
        INSERT INTO backtest_trades (run_id, trade_time, ticker, side, qty, price, fee, slippage_bps)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (run_id, "2026-01-10T00:00:00Z", "AAPL", "buy", 1.0, 100.0, 0.0, 5.0),
    )
    conn.execute(
        """
        INSERT INTO backtest_equity_snapshots (run_id, snapshot_time, cash, market_value, equity, realized_pnl, unrealized_pnl)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (run_id, "2026-01-10T00:00:00Z", 900.0, 110.0, 1010.0, 0.0, 10.0),
    )
    conn.execute(
        """
        INSERT INTO walk_forward_groups (
            grouping_key, account_id, strategy_name, run_name_prefix, start_date, end_date,
            test_months, step_months, window_count, average_return_pct, median_return_pct,
            best_return_pct, worst_return_pct, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "acct_delete_wf",
            account_id,
            "trend",
            "wf-del",
            "2026-01-01",
            "2026-01-31",
            1,
            1,
            1,
            1.0,
            1.0,
            1.0,
            1.0,
            utc_now_iso(),
        ),
    )
    group = conn.execute(
        "SELECT id FROM walk_forward_groups WHERE grouping_key = ?",
        ("acct_delete_wf",),
    ).fetchone()
    assert group is not None
    conn.execute(
        """
        INSERT INTO walk_forward_group_runs (group_id, run_id, window_index, window_start, window_end, total_return_pct)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (int(group["id"]), run_id, 1, "2026-01-01", "2026-01-31", 1.0),
    )
    conn.commit()

    counts = services_admin.delete_account_and_dependents("acct_delete")
    assert counts == {
        "accounts": 1,
        "trades": 1,
        "equitySnapshots": 1,
        "backtestRuns": 1,
        "backtestTrades": 1,
        "backtestEquitySnapshots": 1,
    }

    assert conn.execute("SELECT COUNT(*) AS n FROM accounts WHERE id = ?", (account_id,)).fetchone()["n"] == 0
    assert conn.execute("SELECT COUNT(*) AS n FROM trades WHERE account_id = ?", (account_id,)).fetchone()["n"] == 0
    assert conn.execute("SELECT COUNT(*) AS n FROM equity_snapshots WHERE account_id = ?", (account_id,)).fetchone()["n"] == 0
    assert conn.execute("SELECT COUNT(*) AS n FROM backtest_runs WHERE account_id = ?", (account_id,)).fetchone()["n"] == 0
    assert conn.execute("SELECT COUNT(*) AS n FROM walk_forward_groups WHERE account_id = ?", (account_id,)).fetchone()["n"] == 0
    assert conn.execute("SELECT COUNT(*) AS n FROM walk_forward_group_runs WHERE run_id = ?", (run_id,)).fetchone()["n"] == 0
