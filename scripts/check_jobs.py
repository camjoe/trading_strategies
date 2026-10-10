#!/usr/bin/env python3
"""Report the status of every monitored runtime job (trading + governance + backup).

The job list and per-job status come from
``trading.services.operations.job_status``, the same source the web Admin panel
reads, so the two never disagree on which jobs exist.

Usage:
    python scripts/check_jobs.py
    python scripts/check_jobs.py --run-missing    # also trigger unhealthy jobs
"""

from __future__ import annotations

import argparse
import subprocess
import sys

from common.git import get_repo_root
from trading.interfaces.runtime.jobs.job_helpers import logs_dir_for_repo
from trading.services.operations.job_status import JobStatus, evaluate_all_jobs

REPO_ROOT = get_repo_root(__file__)
LOGS_DIR = logs_dir_for_repo(REPO_ROOT)

# The daily run must complete every trading day; the others are reported but a
# not-yet-run weekly/monthly job is expected, not a failure. A job that STARTED
# but never wrote its sentinel ("warning") is a real failure at any cadence.
DAILY_MUST_RUN_KEY = "daily_paper_trading"

_TRIGGER_TIMEOUT_SECONDS = 300
_OK = "✅"
_WARN = "⚠️ "
_ERR = "❌"


def _use_utf8_stdout() -> None:
    """Keep the report readable on consoles that default to cp1252."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def is_unhealthy(status: JobStatus) -> bool:
    if status.status == "warning":
        return True
    return status.job.key == DAILY_MUST_RUN_KEY and status.status != "ok"


def _icon(status: JobStatus) -> str:
    if status.status == "ok":
        return _OK
    if status.status == "warning":
        return _WARN
    return _ERR


def _run_command(status: JobStatus) -> list[str]:
    return [sys.executable, "-m", status.job.module, *status.job.args]


def _print_status(status: JobStatus) -> None:
    print(f"\n{'─' * 50}")
    print(f"  {_icon(status)} {status.job.label}  ({status.job.cadence}, {status.window_label})")
    if status.status == "ok":
        print("  Completed this period.")
    elif status.status == "warning":
        print("  Started this period but the success sentinel is missing — may have failed.")
    else:
        print("  No completed run for this period.")
    if status.last_success_log is not None:
        print(f"  Last success log: {status.last_success_log.name}")
    else:
        print("  Last success   : never found in logs")
    if is_unhealthy(status):
        print(f"  Run manually   : {' '.join(_run_command(status))}")


def _trigger(status: JobStatus) -> None:
    print(f"\n  ▶  Triggering {status.job.label}…")
    try:
        result = subprocess.run(_run_command(status), cwd=str(REPO_ROOT), timeout=_TRIGGER_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        print(f"  {_ERR}  {status.job.label} timed out after {_TRIGGER_TIMEOUT_SECONDS} seconds.")
        return
    if result.returncode == 0:
        print(f"  {_OK}  {status.job.label} completed successfully.")
    else:
        print(f"  {_ERR}  {status.job.label} exited with code {result.returncode}.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check the status of monitored runtime jobs.")
    parser.add_argument(
        "--run-missing",
        action="store_true",
        help="Trigger any unhealthy job (the daily run if it has not completed today, or any job that started but did not finish).",
    )
    args = parser.parse_args()

    _use_utf8_stdout()
    print(f"\n{'=' * 50}")
    print("  Runtime Job Status")
    print(f"{'=' * 50}")

    statuses = evaluate_all_jobs(logs_dir=LOGS_DIR)
    for status in statuses:
        _print_status(status)

    unhealthy = [status for status in statuses if is_unhealthy(status)]
    print(f"\n{'─' * 50}\n")

    if args.run_missing:
        for status in unhealthy:
            _trigger(status)
        statuses = evaluate_all_jobs(logs_dir=LOGS_DIR)
        unhealthy = [status for status in statuses if is_unhealthy(status)]
    elif unhealthy:
        print("  Tip: pass --run-missing to trigger the unhealthy jobs above.\n")

    return 0 if not unhealthy else 1


if __name__ == "__main__":
    sys.exit(main())
