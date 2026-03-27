#!/usr/bin/env python3
"""Run daily account snapshots with idempotency guard, retries, and metadata output."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

_BOOTSTRAP_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_BOOTSTRAP_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOOTSTRAP_REPO_ROOT))

REPO_ROOT = _BOOTSTRAP_REPO_ROOT

from trading.database.db_config import get_db_path  # noqa: E402

COMPLETE_SENTINEL = "COMPLETE: Daily snapshot run succeeded."
TRANSIENT_ERROR_TOKENS = (
    "temporarily unavailable",
    "timed out",
    "timeout",
    "connection reset",
    "connection aborted",
    "connection error",
    "temporary failure",
    "try again",
    "rate limit",
    "too many requests",
)


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
    return os.getenv("DAILY_SNAPSHOT_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}


def load_all_account_names() -> list[str]:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT name FROM accounts ORDER BY name ASC").fetchall()
    finally:
        conn.close()
    return [str(row["name"]) for row in rows]


def tee_line(log_path: Path, text: str) -> None:
    print(text)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(text + "\n")


def _day_tag(now: dt.datetime) -> str:
    return now.strftime("%Y%m%d")


def already_completed_today(log_dir: Path, day_tag: str) -> bool:
    logs = sorted(log_dir.glob(f"daily_snapshot_{day_tag}_*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not logs:
        return False
    latest = logs[0]
    try:
        return COMPLETE_SENTINEL in latest.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False


def is_transient_error(output: str) -> bool:
    lowered = output.lower()
    return any(token in lowered for token in TRANSIENT_ERROR_TOKENS)


def run_command(log_path: Path, label: str, args: list[str], cwd: Path) -> tuple[int, str]:
    tee_line(log_path, f"[{dt.datetime.now(dt.timezone.utc).astimezone().isoformat()}] START: {label}")
    process = subprocess.Popen(
        [sys.executable, *args],
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
    )
    assert process.stdout is not None
    lines: list[str] = []
    for line in process.stdout:
        clean = line.rstrip("\n")
        lines.append(clean)
        tee_line(log_path, clean)
    exit_code = process.wait()
    combined_output = "\n".join(lines)
    if exit_code == 0:
        tee_line(log_path, f"[{dt.datetime.now(dt.timezone.utc).astimezone().isoformat()}] DONE: {label}")
    else:
        tee_line(log_path, f"[{dt.datetime.now(dt.timezone.utc).astimezone().isoformat()}] ERROR: {label} exit={exit_code}")
    return exit_code, combined_output


def retry_delay_seconds(base_delay_seconds: float, attempt_number: int) -> float:
    # attempt_number is 1-based for human-readable logging.
    return max(base_delay_seconds, 0.0) * (2 ** (attempt_number - 1))


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
    attempts = max(1, max_attempts)
    started_at = dt.datetime.now(dt.timezone.utc).astimezone().isoformat()

    for attempt in range(1, attempts + 1):
        label = f"Snapshot {account} (attempt {attempt}/{attempts})"
        exit_code, output = run_command_fn(
            log_path,
            label,
            ["-m", "trading.paper_trading", "snapshot", "--account", account],
            repo_root,
        )
        if exit_code == 0:
            return {
                "account": account,
                "status": "success",
                "attempts": attempt,
                "started_at": started_at,
                "finished_at": dt.datetime.now(dt.timezone.utc).astimezone().isoformat(),
                "last_exit_code": exit_code,
            }

        transient = is_transient_error(output)
        if attempt >= attempts or not transient:
            return {
                "account": account,
                "status": "failed",
                "attempts": attempt,
                "started_at": started_at,
                "finished_at": dt.datetime.now(dt.timezone.utc).astimezone().isoformat(),
                "last_exit_code": exit_code,
                "transient": transient,
            }

        delay_seconds = retry_delay_seconds(base_backoff_seconds, attempt)
        tee_line(
            log_path,
            (
                f"[{dt.datetime.now(dt.timezone.utc).astimezone().isoformat()}] RETRY: "
                f"account={account} attempt={attempt} delay_seconds={delay_seconds:.2f}"
            ),
        )
        sleep_fn(delay_seconds)

    return {
        "account": account,
        "status": "failed",
        "attempts": attempts,
        "started_at": started_at,
        "finished_at": dt.datetime.now(dt.timezone.utc).astimezone().isoformat(),
        "last_exit_code": 1,
        "transient": False,
    }


def write_artifact(artifact_path: Path, payload: dict[str, object]) -> None:
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


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

    repo_root = REPO_ROOT
    log_dir = repo_root / "local" / "logs"
    output_dir = repo_root / "local" / "exports" / "daily_snapshots"
    log_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    now = dt.datetime.now()
    day_tag = _day_tag(now)
    timestamp = now.strftime("%Y%m%d_%H%M%S")
    log_path = log_dir / f"daily_snapshot_{day_tag}_{timestamp}.log"
    artifact_path = output_dir / f"daily_snapshot_{timestamp}.json"

    all_accounts = load_all_account_names()
    if args.accounts.strip().lower() == "all":
        accounts = all_accounts
    else:
        requested = [item.strip() for item in args.accounts.split(",") if item.strip()]
        known = set(all_accounts)
        missing = [name for name in requested if name not in known]
        if missing:
            print(f"Unknown account(s): {', '.join(missing)}", file=sys.stderr)
            return 1
        accounts = requested

    if not accounts:
        print("No accounts specified.", file=sys.stderr)
        return 1

    run_meta = {
        "job": "daily_snapshot",
        "run_source": args.run_source,
        "force_run": bool(args.force_run),
        "day_tag": day_tag,
        "accounts": accounts,
        "max_attempts": args.max_attempts,
        "backoff_seconds": args.backoff_seconds,
        "log_path": str(log_path.relative_to(repo_root)),
        "artifact_path": str(artifact_path.relative_to(repo_root)),
        "started_at": dt.datetime.now(dt.timezone.utc).astimezone().isoformat(),
    }
    tee_line(log_path, f"[{dt.datetime.now(dt.timezone.utc).astimezone().isoformat()}] RUN META: {json.dumps(run_meta, sort_keys=True)}")

    if not args.force_run and already_completed_today(log_dir, day_tag):
        message = "Daily snapshot already completed today; skipping duplicate run."
        tee_line(log_path, f"[{dt.datetime.now(dt.timezone.utc).astimezone().isoformat()}] SKIP: {message}")
        payload = {
            **run_meta,
            "status": "skipped",
            "skip_reason": "already-completed-today",
            "results": [],
            "finished_at": dt.datetime.now(dt.timezone.utc).astimezone().isoformat(),
        }
        write_artifact(artifact_path, payload)
        return 0

    results: list[dict[str, object]] = []
    failed = False
    for account in accounts:
        result = run_snapshot_with_retry(
            log_path=log_path,
            repo_root=repo_root,
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
                    f"[{dt.datetime.now(dt.timezone.utc).astimezone().isoformat()}] "
                    f"ERROR: Snapshot failed for account={account} "
                    f"attempts={result['attempts']} transient={result.get('transient', False)}"
                ),
            )
            break

    if not failed:
        tee_line(log_path, f"[{dt.datetime.now(dt.timezone.utc).astimezone().isoformat()}] {COMPLETE_SENTINEL}")

    payload = {
        **run_meta,
        "status": "success" if not failed else "failed",
        "results": results,
        "finished_at": dt.datetime.now(dt.timezone.utc).astimezone().isoformat(),
    }
    write_artifact(artifact_path, payload)
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
