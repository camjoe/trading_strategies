import pytest

from tests.support.evaluation import (
    insert_optimization_experiment,
    insert_run,
    insert_snapshot,
)
from trading.services.accounts import create_account, get_account
from trading.services.evaluation import fetch_strategy_evaluation


def test_fetch_strategy_evaluation_assembles_walk_forward_evidence_from_experiment_windows(conn) -> None:
    create_account(conn, "acct_eval_walk_forward", "trend_v1", 1000.0, "SPY")
    account = get_account(conn, "acct_eval_walk_forward")

    # Two OOS windows returning +1% and +2%; the evidence derives both from the
    # runs' equity marks rather than any stored aggregate.
    run_ids = [
        insert_run(
            conn,
            account_id=account["id"],
            strategy_name="trend_v1",
            run_name="wfo_eval_01",
        ),
        insert_run(
            conn,
            account_id=account["id"],
            strategy_name="trend_v1",
            run_name="wfo_eval_02",
        ),
    ]
    for run_id, ending_equity in zip(run_ids, (1010.0, 1020.0)):
        insert_snapshot(conn, run_id=run_id, snapshot_time="2026-01-01T00:00:00Z", equity=1000.0)
        insert_snapshot(conn, run_id=run_id, snapshot_time="2026-01-31T00:00:00Z", equity=ending_equity)

    insert_optimization_experiment(
        conn,
        account_id=account["id"],
        strategy_name="trend_v1",
        window_run_ids=run_ids,
    )

    artifact = fetch_strategy_evaluation(conn, account_name="acct_eval_walk_forward")

    assert artifact.walk_forward.available is True
    assert artifact.walk_forward.window_returns == pytest.approx([1.0, 2.0])
    assert artifact.walk_forward.average_return_pct == pytest.approx(1.5)
    assert artifact.walk_forward.best_return_pct == pytest.approx(2.0)
    assert artifact.walk_forward.worst_return_pct == pytest.approx(1.0)
    assert "missing_walk_forward_evidence" not in artifact.diagnostics.data_gaps


def test_walk_forward_evidence_is_absent_without_an_experiment(conn) -> None:
    create_account(conn, "acct_eval_no_experiment", "trend_v1", 1000.0, "SPY")

    artifact = fetch_strategy_evaluation(conn, account_name="acct_eval_no_experiment")

    assert artifact.walk_forward.available is False
    assert artifact.walk_forward.window_returns == []
    assert "missing_walk_forward_evidence" in artifact.diagnostics.data_gaps
