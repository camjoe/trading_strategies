from __future__ import annotations

import pytest

from common.time import utc_now_iso
from paper_trading_web.backend.services import admin as services_admin
from paper_trading_web.backend.services.admin import create_account_with_rotation
from trading.domain import AccountAlreadyExistsError
from trading.domain.exceptions import NotFoundError
from trading.repositories.snapshots import EquitySnapshotRepository


def test_delete_managed_account_not_found_raises(conn) -> None:
    with pytest.raises(NotFoundError):
        services_admin.delete_managed_account("missing")


def test_delete_managed_account_removes_related_rows(conn, create_account_row) -> None:
    account_id = create_account_row("acct_delete")
    from tests.support.fills import seed_fill_event

    seed_fill_event(
        conn,
        account_id=account_id,
        ticker="AAPL",
        side="buy",
        qty=1.0,
        price=100.0,
        trade_time="2026-01-02T00:00:00Z",
    )
    EquitySnapshotRepository(conn).insert(
        account_id=account_id,
        snapshot_time="2026-01-02T00:00:00Z",
        cash=900.0,
        market_value=100.0,
        equity=1000.0,
        realized_pnl=0.0,
        unrealized_pnl=0.0,
    )
    conn.execute(
        """
        INSERT INTO backtest_runs (
            account_id, run_name, start_date, end_date, created_at,
            slippage_bps, fee_per_trade, tickers_file
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            account_id,
            "run-del",
            "2026-01-01",
            "2026-01-31",
            utc_now_iso(),
            5.0,
            0.0,
            "src/infrastructure/config/trade_universe.txt",
        ),
    )
    run = conn.execute("SELECT id FROM backtest_runs WHERE account_id = ?", (account_id,)).fetchone()
    assert run is not None
    run_id = int(run["id"])

    conn.execute(
        """
        INSERT INTO backtest_executions (run_id, execution_date, ticker, side, qty, price, fee, slippage_bps)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (run_id, "2026-01-10T00:00:00Z", "AAPL", "buy", 1.0, 100.0, 0.0, 5.0),
    )
    conn.execute(
        """
        INSERT INTO backtest_equity_snapshots (
            run_id, snapshot_date, cash, market_value, equity, realized_pnl, unrealized_pnl
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (run_id, "2026-01-10T00:00:00Z", 900.0, 110.0, 1010.0, 0.0, 10.0),
    )
    conn.execute(
        """
        INSERT INTO walk_forward_experiments (
            experiment_key, account_id, run_name_prefix, start_date, end_date,
            test_months, step_months, window_count, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "acct_delete_wf",
            account_id,
            "wf-del",
            "2026-01-01",
            "2026-01-31",
            1,
            1,
            1,
            utc_now_iso(),
        ),
    )
    group = conn.execute(
        "SELECT id FROM walk_forward_experiments WHERE experiment_key = ?",
        ("acct_delete_wf",),
    ).fetchone()
    assert group is not None
    conn.execute(
        """
        INSERT INTO walk_forward_windows (
            experiment_id, run_id, window_index, window_start, window_end, total_return_pct
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (int(group["id"]), run_id, 1, "2026-01-01", "2026-01-31", 1.0),
    )
    conn.commit()

    deleted_name = services_admin.delete_managed_account("acct_delete")
    assert deleted_name == "acct_delete"

    assert conn.execute("SELECT COUNT(*) AS n FROM accounts WHERE id = ?", (account_id,)).fetchone()["n"] == 0
    assert conn.execute("SELECT COUNT(*) AS n FROM orders WHERE account_id = ?", (account_id,)).fetchone()["n"] == 0
    assert (
        conn.execute(
            "SELECT COUNT(*) AS n FROM equity_snapshots s JOIN books b ON b.id = s.book_id WHERE b.account_id = ?",
            (account_id,),
        ).fetchone()["n"]
        == 0
    )
    assert (
        conn.execute("SELECT COUNT(*) AS n FROM backtest_runs WHERE account_id = ?", (account_id,)).fetchone()["n"]
        == 0
    )
    assert (
        conn.execute(
            "SELECT COUNT(*) AS n FROM walk_forward_experiments WHERE account_id = ?", (account_id,)
        ).fetchone()["n"]
        == 0
    )
    assert (
        conn.execute("SELECT COUNT(*) AS n FROM walk_forward_windows WHERE run_id = ?", (run_id,)).fetchone()["n"] == 0
    )


def test_create_account_with_rotation_wraps_duplicate_error(conn, monkeypatch) -> None:
    from paper_trading_web.backend.account_contract import AdminCreateAccountCommand

    command = AdminCreateAccountCommand(
        name="acct_dup",
        strategy="trend",
        initial_cash=1000.0,
        benchmark_ticker="SPY",
        config_values={},
        rotation_settings={},
    )

    def _raise_duplicate(*_args, **_kwargs) -> None:
        raise AccountAlreadyExistsError("already exists")

    monkeypatch.setattr(
        "paper_trading_web.backend.services.admin.create_account",
        _raise_duplicate,
    )

    with pytest.raises(ValueError, match="already exists"):
        create_account_with_rotation(conn, command)
