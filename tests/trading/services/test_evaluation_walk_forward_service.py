import pytest

from trading.services.accounts import create_account, get_account
from trading.services.evaluation import fetch_strategy_evaluation
from tests.support import (
    insert_backtest_run,
    insert_backtest_snapshot,
    insert_walk_forward_grouping,
)


def test_fetch_strategy_evaluation_assembles_walk_forward_evidence_from_grouped_runs(conn) -> None:
    create_account(conn, "acct_eval_walk_forward", "trend_v1", 1000.0, "SPY")
    account = get_account(conn, "acct_eval_walk_forward")

    run_ids = [
        insert_backtest_run(
            conn,
            account_id=account["id"],
            strategy_name="trend_v1",
            run_name="wf_eval_01",
        ),
        insert_backtest_run(
            conn,
            account_id=account["id"],
            strategy_name="trend_v1",
            run_name="wf_eval_02",
        ),
    ]
    for run_id in run_ids:
        insert_backtest_snapshot(conn, run_id=run_id, snapshot_time="2026-01-01T00:00:00Z", equity=1000.0)
        insert_backtest_snapshot(conn, run_id=run_id, snapshot_time="2026-01-31T00:00:00Z", equity=1010.0)

    insert_walk_forward_grouping(
        conn,
        run_ids=run_ids,
        average_return_pct=1.5,
        median_return_pct=1.5,
        best_return_pct=2.0,
        worst_return_pct=1.0,
    )

    artifact = fetch_strategy_evaluation(conn, account_name="acct_eval_walk_forward")

    assert artifact.walk_forward.available is True
    assert artifact.walk_forward.grouped is True
    assert artifact.walk_forward.run_ids == run_ids
    assert artifact.walk_forward.average_return_pct == pytest.approx(1.5)
    assert artifact.walk_forward.best_return_pct == pytest.approx(2.0)
    assert "walk_forward_grouping_not_persisted" not in artifact.diagnostics.data_gaps
