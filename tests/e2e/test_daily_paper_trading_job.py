"""End-to-end test for the daily paper-trading runtime job.

Covers the core capability "runtime scheduler jobs" from ``docs/overview.md``:
a scheduler job runs as its own process. The test drives the daily
``run_auto_trades`` job through its ``main`` entrypoint against a real database
and the deterministic demo provider — real argument parsing, provider and
broker wiring, database session, per-account reporting, and exit code.

The job declines to submit outside US regular equity hours, so the trade count
depends on the clock; the exit code and the per-account report line do not, and
those are what the test pins.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from infrastructure.database.connection import ensure_db
from trading.services.accounts.mutations import create_account
from trading.services.strategy_catalog.seeding import seed_strategy_catalog


def test_daily_paper_trading_job_runs_and_reports_per_account(
    cli_backend: Path,  # noqa: ARG001 — activates the backend + demo provider
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    seed = ensure_db()
    try:
        seed_strategy_catalog(seed)
        create_account(seed, "acct_job", "trend", 10_000.0, "SPY")
        seed.commit()
    finally:
        seed.close()

    from trading.interfaces.runtime.jobs.daily.paper_trading import run_auto_trades as job

    monkeypatch.setattr(sys, "argv", ["run_auto_trades", "--accounts", "acct_job", "--seed", "1"])
    exit_code = job.main()

    assert exit_code == 0
    assert "acct_job:" in capsys.readouterr().out
