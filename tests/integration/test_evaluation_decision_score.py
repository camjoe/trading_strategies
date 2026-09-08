"""Integration test for the canonical evaluation decision score.

Covers the core capability "canonical evaluation" from ``docs/overview.md``:
backtest, walk-forward, and paper evidence fuse into one confidence and a
blended decision score. The test seeds real evidence through the repository
helpers, then reads the fused artifact and its derived decision score. Nothing
is stubbed.
"""

from __future__ import annotations

import sqlite3

from tests.support.evaluation import (
    insert_account_snapshot,
    insert_optimization_experiment,
    insert_run,
    insert_snapshot,
    insert_trade,
)
from trading.domain.evaluation.decision_score import derive_decision_score
from trading.services.accounts.mutations import create_account, get_account
from trading.services.evaluation.queries import fetch_strategy_evaluation
from trading.services.strategy_catalog.seeding import seed_strategy_catalog

STRATEGY = "trend"


def test_evaluation_fuses_evidence_into_a_decision_score(conn: sqlite3.Connection) -> None:
    seed_strategy_catalog(conn)
    create_account(conn, "acct_eval_int", STRATEGY, 1_000.0, "SPY")
    account = get_account(conn, "acct_eval_int")

    # Backtest evidence: a run with a rising equity curve and one trade.
    run_id = insert_run(conn, account_id=account.id, strategy_name=STRATEGY)
    insert_snapshot(conn, run_id=run_id, snapshot_time="2026-01-01T00:00:00Z", equity=1_000.0)
    insert_snapshot(conn, run_id=run_id, snapshot_time="2026-01-31T00:00:00Z", equity=1_120.0)
    insert_trade(conn, run_id=run_id, trade_time="2026-01-15")

    # Walk-forward evidence: one completed optimizer experiment with a window.
    window_run_id = insert_run(conn, account_id=account.id, strategy_name=STRATEGY, run_name="wf-window-1")
    insert_snapshot(conn, run_id=window_run_id, snapshot_time="2026-02-01T00:00:00Z", equity=1_000.0)
    insert_snapshot(conn, run_id=window_run_id, snapshot_time="2026-02-28T00:00:00Z", equity=1_050.0)
    insert_optimization_experiment(
        conn,
        account_id=account.id,
        strategy_name=STRATEGY,
        holdout_run_id=run_id,
        window_run_ids=[window_run_id],
    )

    # Paper evidence: an account equity snapshot.
    insert_account_snapshot(
        conn,
        account_id=account.id,
        snapshot_time="2026-03-01T00:00:00Z",
        cash=1_100.0,
        market_value=0.0,
        equity=1_100.0,
        realized_pnl=100.0,
        unrealized_pnl=0.0,
    )
    conn.commit()

    artifact = fetch_strategy_evaluation(conn, account_name="acct_eval_int", strategy_name=STRATEGY)

    assert artifact.backtest.available is True
    assert artifact.walk_forward.available is True

    decision = derive_decision_score(artifact)
    assert decision.has_evidence is True
    assert decision.score is not None
    assert decision.confidence > 0.0
