from __future__ import annotations

import sqlite3
from collections.abc import Callable
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from paper_trading_web.backend.schemas.strategy_lab import MAX_CANDIDATE_BUDGET

from backtesting.optimizer_models import (
    OptimizationExperimentInsert,
    OptimizationSummary,
    OptimizationTrialInsert,
    OptimizationWindowInsert,
)
from backtesting.repositories.optimization_repository import (
    insert_experiment,
    insert_trial,
    insert_window,
)
from tests.support.evaluation import insert_backtest_run
from tests.support.strategies import ensure_strategy_id_for_label


def _seed_experiment_with_audit(conn: sqlite3.Connection, *, account_name: str) -> tuple[int, int]:
    """Seed one completed experiment with a single window and three candidates.

    Returns ``(experiment_id, oos_run_id)`` — the window's OOS run is a real
    ``backtest_runs`` row because the window carries a foreign key to it.
    """
    account_id = int(conn.execute("SELECT id FROM accounts WHERE name = ?", (account_name,)).fetchone()["id"])
    oos_run_id = insert_backtest_run(conn, account_id=account_id, strategy_name="trend", run_name="wfo_w01")
    experiment_id = insert_experiment(
        conn,
        OptimizationExperimentInsert(
            account_id=account_id,
            strategy_id=ensure_strategy_id_for_label(conn, "trend"),
            primitive="trend",
            objective_name="calmar_v1",
            search_space_json='{"fast_window": [5, 10, 15]}',
            candidate_budget=8,
            train_months=12,
            test_months=1,
            step_months=1,
            holdout_months=6,
            warmup_months=6,
            start_date="2025-01-01",
            end_date="2026-03-31",
            window_count=1,
            winner_params_json='{"fast_window": 10}',
            # Winner beats the default on the OOS mean, in a majority of windows,
            # and on the holdout, so the gate preview must report PASS.
            oos_mean_winner_return_pct=4.0,
            oos_mean_baseline_return_pct=1.0,
            oos_windows_beat_baseline=1,
            holdout_run_id=None,
            holdout_winner_return_pct=6.0,
            holdout_baseline_return_pct=2.0,
        ),
        created_at="2026-04-01T00:00:00Z",
    )
    window_id = insert_window(
        conn,
        OptimizationWindowInsert(
            experiment_id=experiment_id,
            window_index=1,
            train_start="2025-01-01",
            train_end="2025-12-31",
            test_start="2026-01-01",
            test_end="2026-01-31",
            oos_run_id=oos_run_id,
        ),
    )
    candidates = [
        (0, '{"fast_window": 5}', 0.5, True, None, False),
        (1, '{"fast_window": 10}', 2.5, True, None, True),
        (2, '{"fast_window": 15}', None, False, "too_few_trades (1 < 3)", False),
    ]
    for index, params_json, objective, eligible, rejection, selected in candidates:
        insert_trial(
            conn,
            OptimizationTrialInsert(
                window_id=window_id,
                candidate_index=index,
                params_json=params_json,
                params_hash=f"hash{index}",
                objective_value=objective,
                annualized_return_pct=objective,
                max_drawdown_pct=-5.0,
                trade_count=1 if rejection else 9,
                eligible=eligible,
                rejection_reason=rejection,
                selected=selected,
            ),
        )
    conn.commit()
    return experiment_id, oos_run_id


def test_strategy_catalog_lists_primitives_and_supports_draft_lifecycle(api_client: TestClient) -> None:
    catalog = api_client.get("/api/strategy-lab/catalog")
    assert catalog.status_code == 200
    assert catalog.json()["primitives"]

    created = api_client.post(
        "/api/strategy-lab/catalog",
        json={
            "strategyKey": "ui_test_variant",
            "primitive": "trend",
            "params": {"fast_window": 7},
            "description": "UI contract test",
        },
    )
    assert created.status_code == 200
    assert created.json()["strategy"]["status"] == "draft"

    configured = api_client.patch(
        "/api/strategy-lab/catalog/ui_test_variant",
        json={"params": {"slow_window": 25}, "enabled": False},
    )
    assert configured.status_code == 200
    assert configured.json()["strategy"]["params"] == {"fast_window": 7, "slow_window": 25}
    assert configured.json()["strategy"]["enabled"] is False

    frozen = api_client.post("/api/strategy-lab/catalog/ui_test_variant/freeze")
    assert frozen.status_code == 200
    assert frozen.json()["strategy"]["status"] == "frozen"


def test_run_optimization_delegates_to_honest_walk_forward_service(api_client: TestClient) -> None:
    summary = OptimizationSummary(
        strategy="trend",
        account_name="acct",
        objective_name="calmar_v1",
        default_params={},
        experiment_id=42,
    )
    with patch(
        "paper_trading_web.backend.routes.strategy_lab.run_and_persist_optimization",
        Mock(return_value=summary),
    ) as run_mock:
        response = api_client.post(
            "/api/strategy-lab/optimizations",
            json={
                "account": "acct",
                "strategy": "trend",
                "searchSpace": {"fast_window": [5, 10]},
                "lookbackMonths": 24,
            },
        )

    assert response.status_code == 200
    assert response.json()["experimentId"] == 42
    run_mock.assert_called_once()


def test_run_optimization_rejects_a_budget_over_the_synchronous_ceiling(api_client: TestClient) -> None:
    """The route runs its sweep inside the request, so the budget is capped there.

    Rejection must happen during request validation — before the optimizer is
    reached — or the caller waits out the very run the cap exists to prevent.
    """
    with patch(
        "paper_trading_web.backend.routes.strategy_lab.run_and_persist_optimization",
        Mock(),
    ) as run_mock:
        response = api_client.post(
            "/api/strategy-lab/optimizations",
            json={
                "account": "acct",
                "strategy": "trend",
                "searchSpace": {"fast_window": [5, 10]},
                "lookbackMonths": 24,
                "candidateBudget": MAX_CANDIDATE_BUDGET + 1,
            },
        )

    assert response.status_code == 422
    run_mock.assert_not_called()


def test_optimization_detail_nests_every_evaluated_candidate_under_its_window(
    api_client: TestClient,
    api_conn: sqlite3.Connection,
    seed_account: Callable[..., None],
) -> None:
    seed_account("audit_acct")
    experiment_id, oos_run_id = _seed_experiment_with_audit(api_conn, account_name="audit_acct")

    response = api_client.get(f"/api/strategy-lab/optimizations/{experiment_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["experiment"]["accountName"] == "audit_acct"
    assert body["experiment"]["status"] == "completed"
    # The gate preview is computed by the same function a promotion attempt checks.
    assert body["gate"] == {"passed": True, "reasons": []}

    windows = body["windows"]
    assert len(windows) == 1
    assert windows[0]["oosRunId"] == oos_run_id
    assert windows[0]["testStart"] == "2026-01-01"

    trials = windows[0]["trials"]
    # Every candidate is carried, not just the winner — this is the multiple-testing
    # record, and it stays in canonical search order for the caller to rank.
    assert [trial["candidateIndex"] for trial in trials] == [0, 1, 2]
    assert [trial["selected"] for trial in trials] == [False, True, False]
    assert trials[1]["params"] == {"fast_window": 10}
    assert trials[2]["eligible"] is False
    assert trials[2]["rejectionReason"] == "too_few_trades (1 < 3)"


def test_optimization_detail_reports_failed_experiments_without_an_audit_tree(
    api_client: TestClient,
    api_conn: sqlite3.Connection,
    seed_account: Callable[..., None],
) -> None:
    seed_account("failed_acct")
    account_id = int(api_conn.execute("SELECT id FROM accounts WHERE name = ?", ("failed_acct",)).fetchone()["id"])
    experiment_id = insert_experiment(
        api_conn,
        OptimizationExperimentInsert(
            account_id=account_id,
            strategy_id=ensure_strategy_id_for_label(api_conn, "trend"),
            primitive="trend",
            objective_name="calmar_v1",
            search_space_json="{}",
            candidate_budget=8,
            train_months=12,
            test_months=1,
            step_months=1,
            holdout_months=6,
            warmup_months=6,
            start_date="2025-01-01",
            end_date="2026-03-31",
            window_count=2,
            winner_params_json="null",
            oos_mean_winner_return_pct=None,
            oos_mean_baseline_return_pct=None,
            oos_windows_beat_baseline=None,
            holdout_run_id=None,
            holdout_winner_return_pct=None,
            holdout_baseline_return_pct=None,
            status="failed",
            failure_stage="holdout",
            failure_message="boom",
        ),
        created_at="2026-04-01T00:00:00Z",
    )
    api_conn.commit()

    body = api_client.get(f"/api/strategy-lab/optimizations/{experiment_id}").json()

    assert body["experiment"]["status"] == "failed"
    assert body["experiment"]["failureStage"] == "holdout"
    assert body["experiment"]["failureMessage"] == "boom"
    assert body["windows"] == []
    assert body["compoundedOos"] is None
    assert body["manifest"] is None
    # Missing evidence must fail the gate rather than be skipped.
    assert body["gate"]["passed"] is False


def test_optimization_detail_404_for_unknown_experiment(api_client: TestClient) -> None:
    assert api_client.get("/api/strategy-lab/optimizations/999999").status_code == 404
