#!/usr/bin/env python3
"""Run the daily paper-trading job against a fresh sandbox database.

A development check that needs no broker, credentials, or network: the sandbox
is restored from its golden build, every account in it trades on the in-process
simulator, and market data comes from the offline demo provider. Runtime
notifications are switched off. Logs and artifacts go under ``local/dev_runs/``,
where the duplicate-run guard, health check, and burn-in count never look.

Usage:
    python -m scripts.dev_run_daily                          # all sandbox accounts
    python -m scripts.dev_run_daily --ignore-market-hours    # also trade when the market is closed
    python -m scripts.dev_run_daily --accounts sandbox_core  # extra args go to the daily job
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from scripts.fixture_db import checkout_sandbox
from scripts.launch_sandbox import GOLDEN_DATABASE_NAME, SANDBOX_DATABASE_NAME
from trading.interfaces.runtime.jobs.daily.paper_trading.run_auto_trades import DEV_IGNORE_MARKET_HOURS_ENV
from trading.interfaces.runtime.jobs.job_helpers import RUNTIME_ALERT_SMTP_HOST_ENV, RUNTIME_ALERT_WEBHOOK_ENV
from trading.services.fixtures.profiles import SANDBOX_PROFILE

DAILY_JOB_MODULE = "trading.interfaces.runtime.jobs.daily.paper_trading"
# Recorded in the run's log and artifact so a development run is never mistaken for a scheduled one.
DEV_RUN_SOURCE = "dev-sandbox"


def dev_run_root(repo_root: Path) -> Path:
    """The job's ``--repo-root`` for a development run; only its logs and artifacts land here."""
    return repo_root / "local" / "dev_runs"


def build_job_command(repo_root: Path, job_args: list[str]) -> list[str]:
    run_root = dev_run_root(repo_root)
    return [
        sys.executable,
        "-m",
        DAILY_JOB_MODULE,
        "--run-source",
        DEV_RUN_SOURCE,
        "--force-run",
        "--repo-root",
        str(run_root),
        *job_args,
    ]


def parse_args() -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(
        description="Run the daily paper-trading job against a fresh sandbox database.",
        epilog="Any other arguments are passed to the daily job.",
    )
    parser.add_argument(
        "--ignore-market-hours",
        action="store_true",
        help="Submit orders even when the US market is closed (simulator accounts only).",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Regenerate the golden sandbox build before restoring the working copy.",
    )
    return parser.parse_known_args()


def build_job_environment(database_path: Path, *, ignore_market_hours: bool) -> dict[str, str]:
    env = dict(os.environ)
    env.update(
        {
            "TRADING_DB_PATH": str(database_path),
            "TRADING_MARKET_DATA_PROVIDER": "demo",
            "TRADING_EXTERNAL_FEATURES_DISABLED": "1",
        }
    )
    # Each notifier is off while its trigger variable is unset.
    env.pop(RUNTIME_ALERT_WEBHOOK_ENV, None)
    env.pop(RUNTIME_ALERT_SMTP_HOST_ENV, None)
    if ignore_market_hours:
        env[DEV_IGNORE_MARKET_HOURS_ENV] = "1"
    else:
        env.pop(DEV_IGNORE_MARKET_HOURS_ENV, None)
    return env


def main() -> int:
    args, job_args = parse_args()
    repo_root = Path(__file__).resolve().parent.parent
    try:
        database_path, rebuilt = checkout_sandbox(
            repo_root,
            profile=SANDBOX_PROFILE,
            golden_name=GOLDEN_DATABASE_NAME,
            working_name=SANDBOX_DATABASE_NAME,
            force_rebuild=args.rebuild,
        )
    except Exception as exc:
        print(f"Error: could not restore the sandbox database: {exc}", file=sys.stderr)
        return 1
    if rebuilt:
        print(f"Rebuilt golden sandbox build: {repo_root / 'local' / GOLDEN_DATABASE_NAME}")
    print(f"Restored disposable sandbox database: {database_path}")

    run_root = dev_run_root(repo_root)
    run_root.mkdir(parents=True, exist_ok=True)
    print(f"Run logs and artifacts: {run_root / 'local'}")
    env = build_job_environment(database_path, ignore_market_hours=args.ignore_market_hours)
    return subprocess.call(build_job_command(repo_root, job_args), cwd=run_root, env=env)


if __name__ == "__main__":
    raise SystemExit(main())
