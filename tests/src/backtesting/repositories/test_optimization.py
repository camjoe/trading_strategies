from __future__ import annotations

import sqlite3

import pytest

from backtesting.models.optimizer import (
    MANIFEST_V1,
    OptimizationExperimentInsert,
    OptimizationManifestInsert,
    OptimizationTrialInsert,
    OptimizationWindowInsert,
)
from backtesting.repositories.optimization import (
    fetch_experiment_by_id,
    fetch_manifest_for_experiment,
    fetch_trials_for_experiment,
    fetch_windows_for_experiment,
    insert_experiment,
    insert_manifest,
    insert_trial,
    insert_window,
    set_promoted_strategy,
)
from tests.support.repositories import insert_repository_account
from trading.repositories.book_bridge import strategy_id_for_label


def _payload(account_id: int, **overrides) -> OptimizationExperimentInsert:
    base = dict(
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
        window_count=3,
        winner_params_json='{"slow_window": 40}',
        oos_mean_winner_return_pct=1.5,
        oos_mean_baseline_return_pct=1.2,
        oos_windows_beat_baseline=2,
        holdout_run_id=None,
        holdout_winner_return_pct=3.9,
        holdout_baseline_return_pct=4.0,
    )
    base.update(overrides)
    return OptimizationExperimentInsert(**base)


def test_insert_and_fetch_round_trips_fields(conn) -> None:
    account_id = insert_repository_account(conn, name="opt_acct")
    experiment_id = insert_experiment(conn, _payload(account_id), created_at="2026-07-24T00:00:00Z")

    record = fetch_experiment_by_id(conn, experiment_id=experiment_id)
    assert record is not None
    assert record.id == experiment_id
    assert record.account_id == account_id
    assert record.primitive == "trend"
    assert record.winner_params_json == '{"slow_window": 40}'
    assert record.oos_windows_beat_baseline == 2
    assert record.holdout_baseline_return_pct == pytest.approx(4.0)
    assert record.promoted_strategy_id is None  # not promoted yet


def test_fetch_missing_returns_none(conn) -> None:
    assert fetch_experiment_by_id(conn, experiment_id=999) is None


def test_set_promoted_strategy_records_the_link(conn) -> None:
    account_id = insert_repository_account(conn, name="opt_promote")
    experiment_id = insert_experiment(conn, _payload(account_id), created_at="2026-07-24T00:00:00Z")
    strategy_id = strategy_id_for_label(conn, "trend", now_iso="2026-07-24T00:00:00Z")

    set_promoted_strategy(conn, experiment_id=experiment_id, strategy_id=strategy_id)

    record = fetch_experiment_by_id(conn, experiment_id=experiment_id)
    assert record is not None
    assert record.promoted_strategy_id == strategy_id


def _insert_backtest_run(conn: sqlite3.Connection, account_id: int) -> int:
    cursor = conn.execute(
        """
        INSERT INTO backtest_runs (account_id, run_name, start_date, end_date, created_at)
        VALUES (?, 'wfo_w01', '2023-01-01', '2023-02-01', '2026-07-24T00:00:00Z')
        """,
        (account_id,),
    )
    conn.commit()
    assert cursor.lastrowid is not None
    return int(cursor.lastrowid)


def _window(experiment_id: int, oos_run_id: int, **overrides) -> OptimizationWindowInsert:
    base = dict(
        experiment_id=experiment_id,
        window_index=1,
        train_start="2022-01-01",
        train_end="2022-12-31",
        test_start="2023-01-01",
        test_end="2023-01-31",
        oos_run_id=oos_run_id,
    )
    base.update(overrides)
    return OptimizationWindowInsert(**base)


def _trial(window_id: int, **overrides) -> OptimizationTrialInsert:
    base = dict(
        window_id=window_id,
        candidate_index=0,
        params_json='{"slow_window": 20}',
        params_hash="hash-a",
        objective_value=1.5,
        annualized_return_pct=8.0,
        max_drawdown_pct=-5.0,
        trade_count=12,
        eligible=True,
        rejection_reason=None,
        selected=False,
    )
    base.update(overrides)
    return OptimizationTrialInsert(**base)


def test_windows_and_trials_round_trip(conn) -> None:
    account_id = insert_repository_account(conn, name="opt_windows")
    experiment_id = insert_experiment(conn, _payload(account_id), created_at="2026-07-24T00:00:00Z")
    run_id = _insert_backtest_run(conn, account_id)

    window_id = insert_window(conn, _window(experiment_id, run_id))
    insert_trial(conn, _trial(window_id, candidate_index=0, params_hash="hash-a", selected=True))
    insert_trial(
        conn,
        _trial(
            window_id,
            candidate_index=1,
            params_hash="hash-b",
            eligible=False,
            objective_value=None,
            rejection_reason="too_few_trades (1 < 3)",
        ),
    )

    windows = fetch_windows_for_experiment(conn, experiment_id=experiment_id)
    assert [w.window_index for w in windows] == [1]
    assert windows[0].oos_run_id == run_id
    assert windows[0].test_end == "2023-01-31"

    trials = fetch_trials_for_experiment(conn, experiment_id=experiment_id)
    assert [t.candidate_index for t in trials] == [0, 1]
    winner = trials[0]
    assert winner.selected is True and winner.eligible is True
    assert winner.objective_value == pytest.approx(1.5)
    rejected = trials[1]
    assert rejected.selected is False and rejected.eligible is False
    assert rejected.objective_value is None
    assert rejected.rejection_reason == "too_few_trades (1 < 3)"


def test_at_most_one_selected_trial_per_window(conn) -> None:
    account_id = insert_repository_account(conn, name="opt_selected")
    experiment_id = insert_experiment(conn, _payload(account_id), created_at="2026-07-24T00:00:00Z")
    run_id = _insert_backtest_run(conn, account_id)
    window_id = insert_window(conn, _window(experiment_id, run_id))

    insert_trial(conn, _trial(window_id, candidate_index=0, params_hash="hash-a", selected=True))
    with pytest.raises(sqlite3.IntegrityError):
        insert_trial(conn, _trial(window_id, candidate_index=1, params_hash="hash-b", selected=True))


def test_duplicate_candidate_hash_per_window_rejected(conn) -> None:
    account_id = insert_repository_account(conn, name="opt_hash")
    experiment_id = insert_experiment(conn, _payload(account_id), created_at="2026-07-24T00:00:00Z")
    run_id = _insert_backtest_run(conn, account_id)
    window_id = insert_window(conn, _window(experiment_id, run_id))

    insert_trial(conn, _trial(window_id, candidate_index=0, params_hash="dup"))
    with pytest.raises(sqlite3.IntegrityError):
        insert_trial(conn, _trial(window_id, candidate_index=1, params_hash="dup"))


def test_deleting_experiment_cascades_windows_and_trials(conn) -> None:
    account_id = insert_repository_account(conn, name="opt_cascade")
    experiment_id = insert_experiment(conn, _payload(account_id), created_at="2026-07-24T00:00:00Z")
    run_id = _insert_backtest_run(conn, account_id)
    window_id = insert_window(conn, _window(experiment_id, run_id))
    insert_trial(conn, _trial(window_id, selected=True))

    conn.execute("DELETE FROM optimization_experiments WHERE id = ?", (experiment_id,))
    conn.commit()

    assert fetch_windows_for_experiment(conn, experiment_id=experiment_id) == []
    assert fetch_trials_for_experiment(conn, experiment_id=experiment_id) == []


def _manifest(experiment_id: int, **overrides) -> OptimizationManifestInsert:
    base = dict(
        experiment_id=experiment_id,
        manifest_version=MANIFEST_V1,
        account_name="opt_acct",
        book_id=None,
        initial_cash=25_000.0,
        benchmark_ticker="SPY",
        slippage_bps=5.0,
        fee_per_trade=0.0,
        effective_execution_json='{"risk_policy": "none"}',
        tickers_file="universe.txt",
        universe_history_dir=None,
        universe_tickers_json='["AAPL", "MSFT"]',
        universe_size=2,
        market_data_provider="yfinance",
        data_as_of="2026-07-25T00:00:00Z",
        engine_revision="abc123",
    )
    base.update(overrides)
    return OptimizationManifestInsert(**base)


def test_manifest_round_trips_fields(conn) -> None:
    account_id = insert_repository_account(conn, name="opt_manifest")
    experiment_id = insert_experiment(conn, _payload(account_id), created_at="2026-07-24T00:00:00Z")

    insert_manifest(conn, _manifest(experiment_id), created_at="2026-07-25T00:00:00Z")

    record = fetch_manifest_for_experiment(conn, experiment_id=experiment_id)
    assert record is not None
    assert record.manifest_version == MANIFEST_V1
    assert record.initial_cash == pytest.approx(25_000.0)
    assert record.benchmark_ticker == "SPY"
    assert record.universe_size == 2
    assert record.market_data_provider == "yfinance"
    assert record.engine_revision == "abc123"
    assert record.book_id is None


def test_fetch_manifest_missing_returns_none(conn) -> None:
    account_id = insert_repository_account(conn, name="opt_no_manifest")
    experiment_id = insert_experiment(conn, _payload(account_id), created_at="2026-07-24T00:00:00Z")
    assert fetch_manifest_for_experiment(conn, experiment_id=experiment_id) is None


def test_deleting_experiment_cascades_manifest(conn) -> None:
    account_id = insert_repository_account(conn, name="opt_manifest_cascade")
    experiment_id = insert_experiment(conn, _payload(account_id), created_at="2026-07-24T00:00:00Z")
    insert_manifest(conn, _manifest(experiment_id), created_at="2026-07-25T00:00:00Z")

    conn.execute("DELETE FROM optimization_experiments WHERE id = ?", (experiment_id,))
    conn.commit()

    assert fetch_manifest_for_experiment(conn, experiment_id=experiment_id) is None
