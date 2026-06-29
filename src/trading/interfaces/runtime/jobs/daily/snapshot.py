#!/usr/bin/env python3
"""Run daily account snapshots with idempotency guard, retries, and metadata output."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path
from typing import Callable

from common.paths.repo_paths import get_repo_root
from trading.services.accounts import load_runtime_eligible_account_names
from trading.interfaces.runtime.job_status import DAILY_SNAPSHOT_COMPLETE_SENTINEL
from trading.interfaces.runtime.jobs.job_helpers import (
    AttemptOutcome,
    day_tag,
    is_env_truthy,
    latest_log_contains_sentinel,
    logs_dir_for_repo,
    resolve_accounts,
    run_command,
    run_command_with_retry,
    tee_line,
    ts,
    write_artifact,
    CLI_MAIN_MODULE,
)

REPO_ROOT = get_repo_root(__file__)
LOGS_DIR = logs_dir_for_repo(REPO_ROOT)
SNAPSHOTS_EXPORT_DIR = REPO_ROOT / "local" / "exports" / "daily_snapshots"

COMPLETE_SENTINEL = DAILY_SNAPSHOT_COMPLETE_SENTINEL
DAILY_SNAPSHOT_ENABLED_ENV = "DAILY_SNAPSHOT_ENABLED"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run daily account snapshots.")
    parser.add_argument(
        "--accounts",
        default="all",
        help="Comma-separated account names, or 'all' for every account in DB (default: all)",
    )
    parser.add_argument("--force-run", action="store_true", help="Allow duplicate same-day run")
    parser.add_argument("--run-source", default="scheduled-daily-snapshot")
    parser.add_argument(
        "--enable-run",
        action="store_true",
        help="Explicitly enable snapshot execution for this invocation",
    )
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
    return parser.parse_args()


def is_run_enabled(args: argparse.Namespace) -> bool:
    if bool(args.enable_run):
        return True
    return is_env_truthy(DAILY_SNAPSHOT_ENABLED_ENV)


def already_completed_today(log_dir: Path, day_tag_str: str) -> bool:
    return latest_log_contains_sentinel(
        log_dir,
        f"daily_snapshot_{day_tag_str}_*.log",
        COMPLETE_SENTINEL,
    )


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


def main() -> int:
    args = parse_args()
    if args.max_attempts < 1:
        print("--max-attempts must be >= 1", file=sys.stderr)
        return 1
    if args.backoff_seconds < 0:
        print("--backoff-seconds must be >= 0", file=sys.stderr)
        return 1

    if not is_run_enabled(args):
        print(
            "Daily snapshot run is disabled. Use --enable-run or set DAILY_SNAPSHOT_ENABLED=1 to execute.",
            file=sys.stderr,
        )
        return 0

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    SNAPSHOTS_EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    now = dt.datetime.now()
    today = day_tag(now)
    timestamp = now.strftime("%Y%m%d_%H%M%S")
    log_path = LOGS_DIR / f"daily_snapshot_{today}_{timestamp}.log"
    artifact_path = SNAPSHOTS_EXPORT_DIR / f"daily_snapshot_{timestamp}.json"

    all_accounts = load_runtime_eligible_account_names()
    try:
        accounts = resolve_accounts(args.accounts, all_accounts)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if not accounts:
        print("No accounts specified.", file=sys.stderr)
        return 1

    run_meta = {
        "job": "daily_snapshot",
        "run_source": args.run_source,
        "force_run": bool(args.force_run),
        "day_tag": today,
        "accounts": accounts,
        "max_attempts": args.max_attempts,
        "backoff_seconds": args.backoff_seconds,
        "log_path": str(log_path.relative_to(REPO_ROOT)),
        "artifact_path": str(artifact_path.relative_to(REPO_ROOT)),
        "started_at": ts(),
    }
    tee_line(log_path, f"[{ts()}] RUN META: {json.dumps(run_meta, sort_keys=True)}")

    if not args.force_run and already_completed_today(LOGS_DIR, today):
        message = "Daily snapshot already completed today; skipping duplicate run."
        tee_line(log_path, f"[{ts()}] SKIP: {message}")
        payload = {
            **run_meta,
            "status": "skipped",
            "skip_reason": "already-completed-today",
            "results": [],
            "finished_at": ts(),
        }
        write_artifact(artifact_path, payload)
        return 0

    results: list[dict[str, object]] = []
    failed = False
    for account in accounts:
        result = run_snapshot_with_retry(
            log_path=log_path,
            repo_root=REPO_ROOT,
            account=account,
            max_attempts=args.max_attempts,
            base_backoff_seconds=args.backoff_seconds,
        )
        results.append(result)
        if result["status"] != "success":
            failed = True
            tee_line(
                log_path,
                (
                    f"[{ts()}] "
                    f"ERROR: Snapshot failed for account={account} "
                    f"attempts={result['attempts']} transient={result.get('transient', False)}"
                ),
            )
            break

    if not failed:
        tee_line(log_path, f"[{ts()}] {COMPLETE_SENTINEL}")

    payload = {
        **run_meta,
        "status": "success" if not failed else "failed",
        "results": results,
        "finished_at": ts(),
    }
    write_artifact(artifact_path, payload)
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
