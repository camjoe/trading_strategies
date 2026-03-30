from __future__ import annotations

import pytest

from trading.accounts import create_account, get_account
from trading.backtesting.services.history_service import fetch_strategy_backtest_returns


def _insert_run_with_snapshots(
    conn,
    *,
    account_id: int,
    strategy_name: str,
    end_date: str,
    start_equity: float,
    end_equity: float,
) -> None:
    conn.execute(
        """
        INSERT INTO backtest_runs (
            account_id, strategy_name, run_name, start_date, end_date,
            slippage_bps, fee_per_trade, warnings, created_at
        )
        VALUES (?, ?, 'test', '2026-01-01', ?, 0.0, 0.0, '[]', '2026-03-01T00:00:00Z')
        """,
        (account_id, strategy_name, end_date),
    )
    run_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]

    conn.execute(
        """
        INSERT INTO backtest_equity_snapshots (
            run_id, snapshot_time, cash, market_value, equity, realized_pnl, unrealized_pnl
        )
        VALUES (?, '2026-03-01T00:00:00Z', 0.0, 0.0, ?, 0.0, 0.0)
        """,
        (run_id, start_equity),
    )
    conn.execute(
        """
        INSERT INTO backtest_equity_snapshots (
            run_id, snapshot_time, cash, market_value, equity, realized_pnl, unrealized_pnl
        )
        VALUES (?, '2026-03-02T00:00:00Z', 0.0, 0.0, ?, 0.0, 0.0)
        """,
        (run_id, end_equity),
    )
    conn.commit()


def test_returns_rows_for_selected_strategies_within_date_range(conn) -> None:
    create_account(conn, "acct", "trend", 10000.0, "SPY")
    account = get_account(conn, "acct")
    assert account is not None

    _insert_run_with_snapshots(
        conn,
        account_id=int(account["id"]),
        strategy_name="trend",
        end_date="2026-03-08",
        start_equity=10000.0,
        end_equity=10500.0,
    )
    _insert_run_with_snapshots(
        conn,
        account_id=int(account["id"]),
        strategy_name="mean_reversion",
        end_date="2026-03-15",
        start_equity=10000.0,
        end_equity=11000.0,
    )

    out = fetch_strategy_backtest_returns(
        conn,
        account_id=int(account["id"]),
        strategy_names=["trend", "mean_reversion"],
        start_day="2026-03-01",
        end_day="2026-03-31",
    )

    assert [name for name, _ret in out] == ["mean_reversion", "trend"]
    assert out[0][1] == pytest.approx(10.0)
    assert out[1][1] == pytest.approx(5.0)


def test_skips_rows_with_invalid_equity_values(conn) -> None:
    create_account(conn, "acct", "trend", 10000.0, "SPY")
    account = get_account(conn, "acct")
    assert account is not None

    _insert_run_with_snapshots(
        conn,
        account_id=int(account["id"]),
        strategy_name="trend",
        end_date="2026-03-08",
        start_equity=0.0,
        end_equity=1000.0,
    )

    out = fetch_strategy_backtest_returns(
        conn,
        account_id=int(account["id"]),
        strategy_names=["trend"],
        start_day="2026-03-01",
        end_day="2026-03-31",
    )

    assert out == []
