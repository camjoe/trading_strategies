#!/usr/bin/env python3
"""Run daily account snapshots with idempotency guard, retries, and metadata output."""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Callable

from trading.interfaces.runtime.job_status import DAILY_SNAPSHOT_COMPLETE_SENTINEL
from trading.interfaces.runtime.jobs.job_helpers import (
    AttemptOutcome,
    CLI_MAIN_MODULE,
    run_command,
    run_command_with_retry,
)
from trading.interfaces.runtime.jobs.job_runner import JobContext, account_job

JOB_NAME = "daily_snapshot"
COMPLETE_SENTINEL = DAILY_SNAPSHOT_COMPLETE_SENTINEL
DAILY_SNAPSHOT_ENABLED_ENV = "DAILY_SNAPSHOT_ENABLED"


def _add_retry_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=3,
        help="Max attempts per account snapshot command (default: 3)",
    )
    parser.add_argument(
        "--backoff-seconds",
        type=float,
        default=2.0,
        help="Base backoff in seconds between retries (default: 2.0)",
    )


def _validate(args: argparse.Namespace) -> str | None:
    if int(args.max_attempts) < 1:
        return "--max-attempts must be >= 1"
    if float(args.backoff_seconds) < 0:
        return "--backoff-seconds must be >= 0"
    return None


def _run_meta(args: argparse.Namespace) -> dict[str, object]:
    return {"max_attempts": int(args.max_attempts), "backoff_seconds": float(args.backoff_seconds)}


def run_snapshot_with_retry(
    *,
    log_path: Path,
    repo_root: Path,
    account: str,
    max_attempts: int,
    base_backoff_seconds: float,
    run_command_fn: Callable[[Path, str, list[str], Path], tuple[int, str]] = run_command,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> dict[str, object]:
    """Run one account's snapshot command with transient-failure retries.

    Success is a zero exit code; all failures are retryable (subject to the
    transient-error and attempt-count checks in `run_command_with_retry`).
    """

    def classify(exit_code: int, _output: str) -> AttemptOutcome:
        return AttemptOutcome(succeeded=exit_code == 0, retryable=True, extras={})

    return run_command_with_retry(
        log_path=log_path,
        repo_root=repo_root,
        account=account,
        command=["-m", CLI_MAIN_MODULE, "snapshot", "--account", account],
        label_prefix="Snapshot",
        max_attempts=max_attempts,
        base_backoff_seconds=base_backoff_seconds,
        classify=classify,
        run_command_fn=run_command_fn,
        sleep_fn=sleep_fn,
    )


@account_job(
    job_name=JOB_NAME,
    sentinel=COMPLETE_SENTINEL,
    period="day",
    description="Run daily account snapshots.",
    per_account=True,
    enabled_env=DAILY_SNAPSHOT_ENABLED_ENV,
    disabled_message=("Daily snapshot run is disabled. Use --enable-run or set DAILY_SNAPSHOT_ENABLED=1 to execute."),
    run_source_default="scheduled-daily-snapshot",
    export_subdir="daily_snapshots",
    label="Snapshot",
    open_db=False,
    add_arguments=_add_retry_args,
    validate=_validate,
    extra_meta=_run_meta,
)
def main(ctx: JobContext, account: str) -> dict[str, object]:
    return run_snapshot_with_retry(
        log_path=ctx.log_path,
        repo_root=ctx.repo_root,
        account=account,
        max_attempts=int(ctx.args.max_attempts),
        base_backoff_seconds=float(ctx.args.backoff_seconds),
    )


if __name__ == "__main__":
    raise SystemExit(main())
