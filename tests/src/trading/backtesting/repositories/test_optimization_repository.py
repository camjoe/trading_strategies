from __future__ import annotations

import pytest

from tests.support.repositories import insert_repository_account
from trading.backtesting.optimizer_models import OptimizationExperimentInsert
from trading.backtesting.repositories.optimization_repository import (
    fetch_experiment_by_id,
    fetch_latest_for_account,
    insert_experiment,
    set_promoted_strategy,
)
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


def test_fetch_latest_for_account_returns_most_recent(conn) -> None:
    account_id = insert_repository_account(conn, name="opt_latest")
    insert_experiment(conn, _payload(account_id), created_at="2026-07-20T00:00:00Z")
    newer = insert_experiment(conn, _payload(account_id), created_at="2026-07-24T00:00:00Z")

    latest = fetch_latest_for_account(conn, account_id=account_id)
    assert latest is not None
    assert latest.id == newer


def test_fetch_latest_is_account_scoped(conn) -> None:
    account_a = insert_repository_account(conn, name="opt_a")
    account_b = insert_repository_account(conn, name="opt_b")
    insert_experiment(conn, _payload(account_a), created_at="2026-07-24T00:00:00Z")

    assert fetch_latest_for_account(conn, account_id=account_b) is None


def test_set_promoted_strategy_records_the_link(conn) -> None:
    account_id = insert_repository_account(conn, name="opt_promote")
    experiment_id = insert_experiment(conn, _payload(account_id), created_at="2026-07-24T00:00:00Z")
    strategy_id = strategy_id_for_label(conn, "trend", now_iso="2026-07-24T00:00:00Z")

    set_promoted_strategy(conn, experiment_id=experiment_id, strategy_id=strategy_id)

    record = fetch_experiment_by_id(conn, experiment_id=experiment_id)
    assert record is not None
    assert record.promoted_strategy_id == strategy_id
