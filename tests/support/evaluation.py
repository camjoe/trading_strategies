from __future__ import annotations

from backtesting.models.optimizer import (
    OptimizationExperimentInsert,
    OptimizationWindowInsert,
)
from backtesting.repositories.optimization import insert_experiment, insert_window
from tests.support.strategies import ensure_strategy_id_for_label
from trading.repositories.snapshots import EquitySnapshotRepository


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
            strategy_id,
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
            ensure_strategy_id_for_label(conn, strategy_name),
            run_name,
            "2026-01-01",
            "2026-01-31",
            "2026-02-01T00:00:00Z",
            5.0,
            0.0,
            "src/infrastructure/config/trade_universes/default.txt",
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
            snapshot_date,
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
        INSERT INTO backtest_executions (
            run_id,
            execution_date,
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


def insert_optimization_experiment(
    conn,
    *,
    account_id: int,
    strategy_name: str,
    holdout_run_id: int | None = None,
    window_run_ids: list[int] | None = None,
) -> int:
    """Seed one completed optimizer experiment — the evaluation evidence source.

    Window OOS returns are *derived* from each linked run's equity marks, so
    callers control them by seeding those runs' snapshots rather than by passing
    return values here.
    """
    window_ids = window_run_ids or []
    experiment_id = insert_experiment(
        conn,
        OptimizationExperimentInsert(
            account_id=account_id,
            strategy_id=ensure_strategy_id_for_label(conn, strategy_name),
            primitive="trend",
            objective_name="calmar_v1",
            search_space_json='{"fast_window": [5, 10]}',
            candidate_budget=8,
            train_months=12,
            test_months=1,
            step_months=1,
            holdout_months=6,
            warmup_months=6,
            start_date="2026-01-01",
            end_date="2026-03-31",
            window_count=len(window_ids),
            winner_params_json='{"fast_window": 10}',
            oos_mean_winner_return_pct=2.0,
            oos_mean_baseline_return_pct=1.0,
            oos_windows_beat_baseline=len(window_ids),
            holdout_run_id=holdout_run_id,
            holdout_winner_return_pct=3.0,
            holdout_baseline_return_pct=1.0,
        ),
        created_at="2026-04-01T00:00:00Z",
    )
    for window_index, run_id in enumerate(window_ids, start=1):
        insert_window(
            conn,
            OptimizationWindowInsert(
                experiment_id=experiment_id,
                window_index=window_index,
                train_start="2025-01-01",
                train_end="2025-12-31",
                test_start=f"2026-0{window_index}-01",
                test_end=f"2026-0{window_index}-28",
                oos_run_id=run_id,
            ),
        )
    return experiment_id


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
    # Snapshots are book-keyed; the repository resolves the default book.
    EquitySnapshotRepository(conn).insert(
        account_id=account_id,
        snapshot_time=snapshot_time,
        cash=cash,
        market_value=market_value,
        equity=equity,
        realized_pnl=realized_pnl,
        unrealized_pnl=unrealized_pnl,
    )


__all__ = [
    "insert_account_snapshot",
    "insert_backtest_run",
    "insert_backtest_snapshot",
    "insert_backtest_trade",
    "insert_optimization_experiment",
]
