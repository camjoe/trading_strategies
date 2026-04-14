from __future__ import annotations

from datetime import date

from trading.backtesting.models import BacktestConfig
from trading.backtesting.repositories.backtest_repository import insert_backtest_run
from trading.backtesting.repositories.walk_forward_repository import (
    fetch_latest_walk_forward_group_for_account_strategy,
    fetch_walk_forward_group_runs,
    insert_walk_forward_group,
    insert_walk_forward_group_run,
)
from trading.services.accounts_service import create_account


def _cfg() -> BacktestConfig:
    return BacktestConfig(
        account_name="acct_walk_forward_repo",
        tickers_file="trading/config/trade_universe.txt",
        universe_history_dir=None,
        start="2026-01-01",
        end="2026-01-31",
        lookback_months=None,
        slippage_bps=5.0,
        fee_per_trade=0.0,
        run_name="wf-repo-test",
        allow_approximate_leaps=False,
    )


def _insert_run(conn, *, account_id: int, start_date: date, end_date: date) -> int:
    return insert_backtest_run(
        conn,
        account_id=account_id,
        strategy_name="trend_v1",
        start_date=start_date,
        end_date=end_date,
        cfg=_cfg(),
        warnings=[],
    )


def test_walk_forward_repository_persists_and_reads_latest_group(conn) -> None:
    create_account(conn, "acct_walk_forward_repo", "trend_v1", 10000.0, "SPY")
    account_id = int(
        conn.execute(
            "SELECT id FROM accounts WHERE name = ?",
            ("acct_walk_forward_repo",),
        ).fetchone()["id"]
    )
    older_run_id = _insert_run(
        conn,
        account_id=account_id,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
    )
    latest_run_ids = [
        _insert_run(
            conn,
            account_id=account_id,
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 28),
        ),
        _insert_run(
            conn,
            account_id=account_id,
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31),
        ),
    ]

    older_group_id = insert_walk_forward_group(
        conn,
        primary_run_id=older_run_id,
        grouping_key="wf-group-older",
        run_name_prefix="older",
        start_date="2026-01-01",
        end_date="2026-01-31",
        test_months=1,
        step_months=1,
        window_count=1,
        average_return_pct=1.0,
        median_return_pct=1.0,
        best_return_pct=1.0,
        worst_return_pct=1.0,
        created_at="2026-04-01T00:00:00Z",
    )
    insert_walk_forward_group_run(
        conn,
        group_id=older_group_id,
        run_id=older_run_id,
        window_index=1,
        window_start="2026-01-01",
        window_end="2026-01-31",
        total_return_pct=1.0,
    )

    latest_group_id = insert_walk_forward_group(
        conn,
        primary_run_id=latest_run_ids[0],
        grouping_key="wf-group-latest",
        run_name_prefix="latest",
        start_date="2026-02-01",
        end_date="2026-03-31",
        test_months=1,
        step_months=1,
        window_count=2,
        average_return_pct=3.0,
        median_return_pct=3.0,
        best_return_pct=4.0,
        worst_return_pct=2.0,
        created_at="2026-05-01T00:00:00Z",
    )
    for window_index, run_id in enumerate(latest_run_ids, start=1):
        insert_walk_forward_group_run(
            conn,
            group_id=latest_group_id,
            run_id=run_id,
            window_index=window_index,
            window_start=f"2026-0{window_index + 1}-01",
            window_end=f"2026-0{window_index + 1}-28",
            total_return_pct=float(window_index + 1),
        )

    latest_group = fetch_latest_walk_forward_group_for_account_strategy(
        conn,
        account_id=account_id,
        strategy_name="trend_v1",
    )

    assert latest_group is not None
    assert latest_group["grouping_key"] == "wf-group-latest"
    assert latest_group["window_count"] == 2
    assert latest_group["average_return_pct"] == 3.0

    latest_group_runs = fetch_walk_forward_group_runs(conn, group_id=int(latest_group["id"]))

    assert [int(item["run_id"]) for item in latest_group_runs] == latest_run_ids
    assert [int(item["window_index"]) for item in latest_group_runs] == [1, 2]
