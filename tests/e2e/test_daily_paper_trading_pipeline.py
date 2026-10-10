"""End-to-end test for the daily paper-trading pipeline the scheduler starts.

The scheduled ``daily_paper_trading`` job is the step DAG in
``trading.interfaces.runtime.jobs.daily.paper_trading``, which runs its trading,
reconcile, snapshot, and comparison steps as child processes. The test runs that
``main`` with no stubs, against a real database and the deterministic demo
provider, so a change that breaks a child module path, a forwarded argument, or
the run artifact fails here.

Child processes do not inherit test stubs, so step 05 obeys the real market-hours
guard and may submit nothing. ``tests/e2e/test_daily_paper_trading_job.py`` covers
the trade path inside step 05.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from common.logging_setup import RUN_ID_ENV
from infrastructure.database.connection import ensure_db
from trading.interfaces.runtime.jobs.daily.paper_trading.dag import DAILY_DAG_STEPS
from trading.interfaces.runtime.jobs.job_helpers import RUNTIME_ALERT_SMTP_HOST_ENV, RUNTIME_ALERT_WEBHOOK_ENV
from trading.services.accounts.mutations import create_account
from trading.services.strategy_catalog.seeding import seed_strategy_catalog

SKIPPED_STEPS = {
    "02_run_signals_all_strategies",
    "03_score_incumbent_vs_challengers",
    "04_rotation_decision",
}


def _seed_job_account() -> None:
    conn = ensure_db()
    try:
        seed_strategy_catalog(conn)
        create_account(conn, "acct_job", "trend", 10_000.0, "SPY")
        conn.commit()
    finally:
        conn.close()


def test_daily_paper_trading_pipeline_runs_every_step_and_writes_its_artifact(
    cli_backend: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_job_account()
    monkeypatch.setenv("TRADING_DB_PATH", str(cli_backend))
    monkeypatch.setenv(RUN_ID_ENV, "e2e-pipeline")
    monkeypatch.delenv(RUNTIME_ALERT_WEBHOOK_ENV, raising=False)
    monkeypatch.delenv(RUNTIME_ALERT_SMTP_HOST_ENV, raising=False)

    from trading.interfaces.runtime.jobs.daily import paper_trading as job

    repo_root = tmp_path / "run_root"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "daily_paper_trading",
            "--accounts",
            "acct_job",
            "--seed",
            "1",
            "--run-source",
            "e2e-test",
            "--repo-root",
            str(repo_root),
        ],
    )
    exit_code = job.main()

    artifacts = list((repo_root / "local" / "exports" / "daily_paper_trading").glob("*.json"))
    assert len(artifacts) == 1
    artifact = json.loads(artifacts[0].read_text(encoding="utf-8"))
    statuses = {step["step"]: step["status"] for step in artifact["step_results"]}

    assert exit_code == 0, f"failed_step={artifact.get('failed_step')} error={artifact.get('error')}"
    assert artifact["status"] == "success"
    assert artifact["accounts"] == ["acct_job"]
    assert artifact["summary"]["accounts"] == 1
    assert artifact["kill_switch_accounts"] == []
    assert statuses == {step: "skipped" if step in SKIPPED_STEPS else "ok" for step, _name in DAILY_DAG_STEPS}
