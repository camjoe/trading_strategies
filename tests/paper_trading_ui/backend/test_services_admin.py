from __future__ import annotations

import pytest
from fastapi import HTTPException

from common.time import utc_now_iso
from paper_trading_ui.backend import services_admin

from tests.paper_trading_ui.backend._service_test_utils import create_test_account


def test_clean_text_and_rotation_schedule_json() -> None:
    assert services_admin.clean_text(None) is None
    assert services_admin.clean_text("   ") is None
    assert services_admin.clean_text("  hello  ") == "hello"

    schedule = services_admin.build_rotation_schedule_json([" trend ", "mean_reversion", "trend", " "])
    assert schedule == '["trend","mean_reversion"]'


def test_delete_account_and_dependents_not_found_raises(conn) -> None:
    with pytest.raises(HTTPException) as exc_info:
        services_admin.delete_account_and_dependents("missing")
    assert exc_info.value.status_code == 404


def test_delete_account_and_dependents_removes_related_rows(conn) -> None:
    account_id = create_test_account(conn, "acct_delete")
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
        (account_id, "run-del", "2026-01-01", "2026-01-31", utc_now_iso(), 5.0, 0.0, "trading/trade_universe.txt"),
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
