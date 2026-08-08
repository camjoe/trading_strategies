"""Compounded OOS aggregation service: reads persisted windows + their OOS run
equity marks and compounds them, returning None when a segment is missing."""

from __future__ import annotations

import sqlite3

import pytest

from backtesting.models.optimizer import OptimizationExperimentInsert, OptimizationWindowInsert
from backtesting.repositories.backtest_repository import insert_backtest_snapshot
from backtesting.repositories.optimization_repository import insert_experiment, insert_window
from backtesting.services.optimizer_aggregation_service import fetch_compounded_oos
from tests.support.repositories import insert_repository_account


def _experiment(conn: sqlite3.Connection, account_id: int) -> int:
    return insert_experiment(
        conn,
        OptimizationExperimentInsert(
            account_id=account_id,
            strategy_id=None,
            primitive="trend",
            objective_name="calmar_v1",
            search_space_json='{"slow_window": [20, 40]}',
            candidate_budget=256,
            train_months=12,
            test_months=1,
            step_months=1,
            holdout_months=6,
            warmup_months=6,
            start_date="2022-01-01",
            end_date="2023-12-31",
            window_count=2,
            winner_params_json='{"slow_window": 40}',
            oos_mean_winner_return_pct=None,
            oos_mean_baseline_return_pct=None,
            oos_windows_beat_baseline=None,
            holdout_run_id=None,
            holdout_winner_return_pct=None,
            holdout_baseline_return_pct=None,
        ),
        created_at="2026-07-25T00:00:00Z",
    )


def _oos_run(conn: sqlite3.Connection, account_id: int, *, first_equity: float, last_equity: float) -> int:
    cursor = conn.execute(
        """
        INSERT INTO backtest_runs (account_id, run_name, purpose, start_date, end_date, created_at)
        VALUES (?, 'wfo_w', 'walk_forward_oos', '2023-01-01', '2023-01-31', '2026-07-25T00:00:00Z')
        """,
        (account_id,),
    )
    run_id = int(cursor.lastrowid)
    conn.commit()
    # Two equity marks: the first and last of the run's curve.
    insert_backtest_snapshot(
        conn,
        run_id=run_id,
        snapshot_time="2023-01-02",
        cash=first_equity,
        market_value=0.0,
        equity=first_equity,
        realized_pnl=0.0,
        unrealized_pnl=0.0,
    )
    insert_backtest_snapshot(
        conn,
        run_id=run_id,
        snapshot_time="2023-01-31",
        cash=last_equity,
        market_value=0.0,
        equity=last_equity,
        realized_pnl=0.0,
        unrealized_pnl=0.0,
    )
    return run_id


def _window(conn, experiment_id, run_id, *, index, test_start, test_end) -> None:
    insert_window(
        conn,
        OptimizationWindowInsert(
            experiment_id=experiment_id,
            window_index=index,
            train_start="2022-01-01",
            train_end="2022-12-31",
            test_start=test_start,
            test_end=test_end,
            oos_run_id=run_id,
        ),
    )


def test_compounds_contiguous_windows(conn) -> None:
    account_id = insert_repository_account(conn, name="chain_ok")
    experiment_id = _experiment(conn, account_id)
    run1 = _oos_run(conn, account_id, first_equity=10_000.0, last_equity=11_000.0)  # +10%
    run2 = _oos_run(conn, account_id, first_equity=10_000.0, last_equity=11_000.0)  # +10%
    _window(conn, experiment_id, run1, index=1, test_start="2023-01-01", test_end="2023-01-31")
    _window(conn, experiment_id, run2, index=2, test_start="2023-02-01", test_end="2023-02-28")

    series = fetch_compounded_oos(conn, experiment_id=experiment_id)

    assert series is not None
    assert series.compounded_return_pct == pytest.approx(21.0)  # compounded, not 20
    assert [p.cumulative_return_pct for p in series.points] == pytest.approx([10.0, 21.0])
    assert not series.has_gaps


def test_flags_gap_between_non_contiguous_windows(conn) -> None:
    account_id = insert_repository_account(conn, name="chain_gap")
    experiment_id = _experiment(conn, account_id)
    run1 = _oos_run(conn, account_id, first_equity=10_000.0, last_equity=10_500.0)
    run2 = _oos_run(conn, account_id, first_equity=10_000.0, last_equity=10_500.0)
    _window(conn, experiment_id, run1, index=1, test_start="2023-01-01", test_end="2023-01-31")
    # March start after a January end — a step longer than the test window.
    _window(conn, experiment_id, run2, index=2, test_start="2023-03-01", test_end="2023-03-31")

    series = fetch_compounded_oos(conn, experiment_id=experiment_id)

    assert series is not None
    assert series.has_gaps
    assert series.points[1].gap_before is True


def test_returns_none_when_a_window_oos_run_has_no_snapshots(conn) -> None:
    account_id = insert_repository_account(conn, name="chain_missing")
    experiment_id = _experiment(conn, account_id)
    # A window whose OOS run exists but has no equity snapshots — no honest segment.
    empty_run = conn.execute(
        """
        INSERT INTO backtest_runs (account_id, run_name, purpose, start_date, end_date, created_at)
        VALUES (?, 'wfo_empty', 'walk_forward_oos', '2023-01-01', '2023-01-31', '2026-07-25T00:00:00Z')
        """,
        (account_id,),
    )
    conn.commit()
    _window(conn, experiment_id, int(empty_run.lastrowid), index=1, test_start="2023-01-01", test_end="2023-01-31")

    assert fetch_compounded_oos(conn, experiment_id=experiment_id) is None


def test_returns_none_when_no_windows_persisted(conn) -> None:
    account_id = insert_repository_account(conn, name="chain_nowindows")
    experiment_id = _experiment(conn, account_id)

    assert fetch_compounded_oos(conn, experiment_id=experiment_id) is None
