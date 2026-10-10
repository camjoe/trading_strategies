"""End-to-end test for the ``backtest`` CLI command.

Covers the core capability "backtesting" from ``docs/overview.md``: the real
CLI entrypoint resolves the account's strategy, runs the strategy signal
function over deterministic demo prices, and persists a completed run tree.
Nothing here is mocked — the assertion reads the row the run wrote.
"""

from __future__ import annotations

from collections.abc import Callable

from infrastructure.database.connection import ensure_db
from trading.services.accounts.mutations import create_account
from trading.services.strategy_catalog.seeding import seed_strategy_catalog


def test_backtest_cli_persists_a_run(run_cli: Callable[..., str]) -> None:
    seed = ensure_db()
    try:
        seed_strategy_catalog(seed)
        create_account(seed, "acct_e2e", "trend", 10_000.0, "SPY")
        seed.commit()
    finally:
        seed.close()

    out = run_cli(
        "backtest",
        "--account",
        "acct_e2e",
        "--start",
        "2025-06-01",
        "--end",
        "2026-03-01",
    )

    assert "Backtest complete: run_id=" in out

    verify = ensure_db()
    try:
        run_count = verify.execute("SELECT COUNT(*) FROM backtest_runs").fetchone()[0]
        account_name = verify.execute(
            """
            SELECT a.name
            FROM backtest_runs r
            JOIN accounts a ON a.id = r.account_id
            """
        ).fetchone()[0]
    finally:
        verify.close()

    assert run_count == 1
    assert account_name == "acct_e2e"
