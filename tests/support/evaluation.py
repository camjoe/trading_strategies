from __future__ import annotations

from trading.backtesting.repositories.walk_forward_repository import (
    insert_walk_forward_group,
    insert_walk_forward_group_run,
)


def insert_backtest_run(
    conn,
    *,
    account_id: int,
    strategy_name: str,
    run_name: str = "evaluation-smoke",
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
            run_name,
            "2026-01-01",
            "2026-01-31",
            "2026-02-01T00:00:00Z",
            5.0,
            0.0,
            "src/infrastructure/config/trade_universe.txt",
            "seeded",
            "warning-a",
        ),
    )
    assert cursor.lastrowid is not None
    return int(cursor.lastrowid)


def insert_backtest_snapshot(conn, *, run_id: int, snapshot_time: str, equity: float) -> None:
    conn.execute(
        """
        INSERT INTO backtest_equity_snapshots (
            run_id,
            snapshot_time,
            cash,
            market_value,
            equity,
            realized_pnl,
            unrealized_pnl
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (run_id, snapshot_time, equity, 0.0, equity, 0.0, 0.0),
    )


def insert_backtest_trade(conn, *, run_id: int, trade_time: str) -> None:
    conn.execute(
        """
        INSERT INTO backtest_trades (
            run_id,
            trade_time,
            ticker,
            side,
            qty,
            price,
            fee,
            slippage_bps,
            note
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (run_id, trade_time, "AAPL", "buy", 1.0, 100.0, 0.0, 5.0, "seeded"),
    )


def insert_walk_forward_grouping(
    conn,
    *,
    run_ids: list[int],
    average_return_pct: float,
    median_return_pct: float,
    best_return_pct: float,
    worst_return_pct: float,
) -> None:
    group_id = insert_walk_forward_group(
        conn,
        primary_run_id=run_ids[0],
        grouping_key="wf-eval-group",
        run_name_prefix="wf-eval",
        start_date="2026-01-01",
        end_date="2026-03-31",
        test_months=1,
        step_months=1,
        window_count=len(run_ids),
        average_return_pct=average_return_pct,
        median_return_pct=median_return_pct,
        best_return_pct=best_return_pct,
        worst_return_pct=worst_return_pct,
        created_at="2026-04-01T00:00:00Z",
    )
    for window_index, run_id in enumerate(run_ids, start=1):
        insert_walk_forward_group_run(
            conn,
            group_id=group_id,
            run_id=run_id,
            window_index=window_index,
            window_start=f"2026-0{window_index}-01",
            window_end=f"2026-0{window_index}-28",
            total_return_pct=float(window_index),
        )


def insert_account_snapshot(
    conn,
    *,
    account_id: int,
    snapshot_time: str,
    cash: float,
    market_value: float,
    equity: float,
    realized_pnl: float,
    unrealized_pnl: float,
) -> None:
    conn.execute(
        """
        INSERT INTO equity_snapshots (
            account_id,
            snapshot_time,
            cash,
            market_value,
            equity,
            realized_pnl,
            unrealized_pnl
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            account_id,
            snapshot_time,
            cash,
            market_value,
            equity,
            realized_pnl,
            unrealized_pnl,
        ),
    )


__all__ = [
    "insert_account_snapshot",
    "insert_backtest_run",
    "insert_backtest_snapshot",
    "insert_backtest_trade",
    "insert_walk_forward_grouping",
]

