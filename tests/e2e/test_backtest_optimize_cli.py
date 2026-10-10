"""End-to-end tests for walk-forward optimization and winner promotion.

Covers the core capability "walk-forward optimization" (``backtest-optimize``)
from ``docs/overview.md`` and the research→variant workflow that promotes an
experiment's winner into a tradeable strategy. Both run through the real CLI
over the deterministic demo provider, so the whole composition — optimizer,
per-window backtests, experiment persistence, and the promotion service — runs
end to end. The service layer already owns the optimizer's behavioral matrix;
these tests cover the CLI, composition, and cross-service seams it cannot.
"""

from __future__ import annotations

from collections.abc import Callable

from infrastructure.database.connection import ensure_db
from trading.repositories.strategies import StrategyRepository
from trading.services.accounts.mutations import create_account
from trading.services.strategy_catalog.seeding import seed_strategy_catalog

# A small grid over a short walk-forward horizon: enough windows to be real,
# small enough to stay fast over deterministic demo data.
_OPTIMIZE_ARGS = (
    "backtest-optimize",
    "--account",
    "acct_opt",
    "--strategy",
    "trend",
    "--search-space",
    '{"fast_window": [5, 10], "slow_window": [20, 30]}',
    "--start",
    "2023-01-01",
    "--end",
    "2024-04-01",
    "--train-months",
    "6",
    "--test-months",
    "1",
    "--step-months",
    "3",
    "--holdout-months",
    "2",
    "--warmup-months",
    "2",
)


def _seed_account() -> None:
    conn = ensure_db()
    try:
        seed_strategy_catalog(conn)
        create_account(conn, "acct_opt", "trend", 10_000.0, "SPY")
        conn.commit()
    finally:
        conn.close()


def _latest_experiment() -> tuple[int, str]:
    conn = ensure_db()
    try:
        row = conn.execute("SELECT id, status FROM optimization_experiments ORDER BY id DESC LIMIT 1").fetchone()
    finally:
        conn.close()
    assert row is not None, "no optimization experiment was persisted"
    return int(row[0]), str(row[1])


def test_backtest_optimize_persists_a_completed_experiment(run_cli: Callable[..., str]) -> None:
    _seed_account()

    out = run_cli(*_OPTIMIZE_ARGS)

    assert "Persisted optimization experiment #" in out
    experiment_id, status = _latest_experiment()
    assert experiment_id > 0
    assert status != "failed"


def test_backtest_optimize_promote_mints_a_variant(run_cli: Callable[..., str]) -> None:
    _seed_account()
    run_cli(*_OPTIMIZE_ARGS)
    experiment_id, status = _latest_experiment()
    assert status != "failed"

    # --allow-no-edge bypasses the quality bar: this test pins the promotion
    # wiring, not whether the demo data happened to beat its own default.
    out = run_cli("backtest-optimize-promote", str(experiment_id), "--key", "opt_trend_v1", "--allow-no-edge")

    assert "Promoted experiment" in out

    verify = ensure_db()
    try:
        record = StrategyRepository(verify).fetch_by_key(strategy_key="opt_trend_v1")
    finally:
        verify.close()

    assert record is not None
    assert record.primitive == "trend"
    assert record.status == "frozen"
