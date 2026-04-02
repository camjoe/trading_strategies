from __future__ import annotations

from datetime import date

from trading.services.accounts_service import create_account
from trading.backtesting.repositories.backtest_repository import (
    insert_backtest_run,
    insert_backtest_snapshot,
    insert_backtest_trade,
)
from trading.backtesting.models import BacktestConfig


def _cfg() -> BacktestConfig:
    return BacktestConfig(
        account_name="acct_repo",
        tickers_file="trading/config/trade_universe.txt",
        universe_history_dir=None,
        start="2026-01-01",
        end="2026-01-31",
        lookback_months=None,
        slippage_bps=5.0,
        fee_per_trade=0.0,
        run_name="repo-test",
        allow_approximate_leaps=False,
    )


def test_backtest_repository_inserts_run_trade_and_snapshot(conn) -> None:
    create_account(conn, "acct_repo", "trend_v1", 10000.0, "SPY")
    account_id = int(conn.execute("SELECT id FROM accounts WHERE name = ?", ("acct_repo",)).fetchone()["id"])

    run_id = insert_backtest_run(
        conn,
        account_id=account_id,
        strategy_name="trend_v1",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        cfg=_cfg(),
        warnings=["w1", "w2"],
    )

    insert_backtest_trade(
        conn,
        run_id=run_id,
        trade_time="2026-01-02",
        ticker="AAPL",
        side="buy",
        qty=1.0,
        price=100.0,
        fee=0.0,
        slippage_bps=5.0,
        note="note",
    )
    insert_backtest_snapshot(
        conn,
        run_id=run_id,
        snapshot_time="2026-01-02",
        cash=9900.0,
        market_value=100.0,
        equity=10000.0,
        realized_pnl=0.0,
        unrealized_pnl=0.0,
    )
    conn.commit()

    run_row = conn.execute("SELECT run_name, warnings FROM backtest_runs WHERE id = ?", (run_id,)).fetchone()
    trades = conn.execute("SELECT COUNT(*) AS n FROM backtest_trades WHERE run_id = ?", (run_id,)).fetchone()
    snaps = conn.execute("SELECT COUNT(*) AS n FROM backtest_equity_snapshots WHERE run_id = ?", (run_id,)).fetchone()

    assert run_row is not None
    assert run_row["run_name"] == "repo-test"
    assert "w1 | w2" == run_row["warnings"]
    assert int(trades["n"]) == 1
    assert int(snaps["n"]) == 1
