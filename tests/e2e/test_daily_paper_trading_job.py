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

import trading.services.auto_trading.runtime as runtime_service
from infrastructure.database.connection import ensure_db
from trading.services.accounts.mutations import create_account
from trading.services.strategy_catalog.seeding import seed_strategy_catalog


def _seed_job_account() -> None:
    conn = ensure_db()
    try:
        seed_strategy_catalog(conn)
        create_account(conn, "acct_job", "trend", 10_000.0, "SPY")
        conn.commit()
    finally:
        conn.close()


def test_daily_paper_trading_job_runs_and_reports_per_account(
    cli_backend: Path,  # noqa: ARG001 — activates the backend + demo provider
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed_job_account()

    from trading.interfaces.runtime.jobs.daily.paper_trading import run_auto_trades as job

    monkeypatch.setattr(sys, "argv", ["run_auto_trades", "--accounts", "acct_job", "--seed", "1"])
    exit_code = job.main()

    assert exit_code == 0
    assert "acct_job:" in capsys.readouterr().out


def test_daily_paper_trading_job_persists_a_run_audit_when_market_is_open(
    cli_backend: Path,  # noqa: ARG001 — activates the backend + demo provider
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The real pipeline reaches persistence, not just exit 0.

    The submission window is forced open — the one clock concession — so the
    run proceeds past the market-hours guard. The job then writes an
    account-keyed ``risk_snapshots`` audit row even on a no-trade run, which
    proves the daily pipeline runs end to end through to persistence with real
    components (provider, broker, universe resolution, gate, audit).
    """
    _seed_job_account()
    monkeypatch.setattr(runtime_service, "is_runtime_submission_window_open", lambda *_a, **_k: True)

    from trading.interfaces.runtime.jobs.daily.paper_trading import run_auto_trades as job

    monkeypatch.setattr(sys, "argv", ["run_auto_trades", "--accounts", "acct_job", "--seed", "1"])
    exit_code = job.main()
    assert exit_code == 0

    verify = ensure_db()
    try:
        account_id = verify.execute("SELECT id FROM accounts WHERE name = 'acct_job'").fetchone()[0]
        audit_count = verify.execute(
            "SELECT COUNT(*) FROM risk_snapshots WHERE account_id = ?", (account_id,)
        ).fetchone()[0]
    finally:
        verify.close()

    assert audit_count >= 1
