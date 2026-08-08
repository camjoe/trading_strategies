import sqlite3

import pytest

from tests.support.evaluation import (
    insert_account_snapshot,
    insert_optimization_experiment,
    insert_run,
    insert_snapshot,
    insert_trade,
)
from trading.services.evaluation import fetch_strategy_evaluation


def test_fetch_strategy_evaluation_assembles_backtest_and_snapshot_evidence(
    conn,
    eval_account: sqlite3.Row,
) -> None:
    # Backtest evidence is the experiment's untouched holdout run, not a
    # standalone backtest over an operator-chosen range.
    run_id = insert_run(conn, account_id=eval_account["id"], strategy_name="trend_v1")
    insert_snapshot(conn, run_id=run_id, snapshot_time="2026-01-01T00:00:00Z", equity=1000.0)
    insert_snapshot(conn, run_id=run_id, snapshot_time="2026-01-15T00:00:00Z", equity=1100.0)
    insert_snapshot(conn, run_id=run_id, snapshot_time="2026-01-31T00:00:00Z", equity=1050.0)
    insert_trade(conn, run_id=run_id, trade_time="2026-01-02T00:00:00Z")
    insert_trade(conn, run_id=run_id, trade_time="2026-01-10T00:00:00Z")
    insert_optimization_experiment(
        conn,
        account_id=eval_account["id"],
        strategy_name="trend_v1",
        holdout_run_id=run_id,
    )

    insert_account_snapshot(
        conn,
        account_id=eval_account["id"],
        snapshot_time="2026-02-01T00:00:00Z",
        cash=800.0,
        market_value=220.0,
        equity=1020.0,
        realized_pnl=10.0,
        unrealized_pnl=20.0,
    )
    conn.commit()

    artifact = fetch_strategy_evaluation(conn, account_name="acct_eval")

    assert artifact.basic.requested_strategy == "trend_v1"
    assert artifact.backtest.available is True
    assert artifact.backtest.run_id == run_id
    assert artifact.backtest.total_return_pct == pytest.approx(5.0)
    assert artifact.backtest.max_drawdown_pct == pytest.approx(-4.545454545454546)
    assert artifact.paper_live.available is True
    assert artifact.paper_live.source_level == "account_snapshot"
    assert artifact.paper_live.return_pct == pytest.approx(2.0)
    assert artifact.confidence.overall_confidence > 0.0
    assert artifact.confidence.blended_score is not None
    assert artifact.confidence.blended_score > artifact.paper_live.return_pct
    assert "missing_walk_forward_evidence" in artifact.diagnostics.data_gaps
    # Backtest evidence exists, so the advisory freshness diagnostic is populated.
    assert artifact.diagnostics.backtest_freshness is not None
    assert artifact.diagnostics.backtest_freshness.available is True
