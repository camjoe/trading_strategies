#!/usr/bin/env python3
"""Check burn-in stability of daily paper-trading runs and report go-live readiness."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path

from common.paths.repo_paths import get_repo_root
from trading.interfaces.runtime.jobs.job_helpers import (
    day_tag,
    latest_log_contains_sentinel,
    logs_dir_for_repo,
    tee_line,
    ts,
    write_artifact,
)
from trading.interfaces.runtime.job_status import (
    BURN_IN_STATUS_COMPLETE_SENTINEL,
    DAILY_RUN_STATUS_FAILED,
    DAILY_RUN_STATUS_SUCCESS,
)

REPO_ROOT = get_repo_root(__file__)
LOGS_DIR = logs_dir_for_repo(REPO_ROOT)

COMPLETE_SENTINEL = BURN_IN_STATUS_COMPLETE_SENTINEL

# Pattern: daily_paper_trading_YYYYMMDD_HHMMSS.json
_ARTIFACT_RE = re.compile(r"^daily_paper_trading_(\d{8})_(\d{6})\.json$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check burn-in stability of daily paper-trading runs.",
    )
    parser.add_argument(
        "--min-consecutive-days",
        type=int,
        default=10,
        help="Minimum consecutive successful daily runs required (default: 10)",
    )
    parser.add_argument(
        "--max-failure-rate-pct",
        type=float,
        default=0.0,
        help="Maximum acceptable failed-step rate over the window in %% (default: 0.0)",
    )
    parser.add_argument(
        "--window-days",
        type=int,
        default=30,
        help="How many calendar days of history to scan for artifacts (default: 30)",
    )
    parser.add_argument(
        "--repo-root",
        default=str(REPO_ROOT),
        help="Repository root path (default: inferred from script location)",
    )
    parser.add_argument(
        "--force-run",
        action="store_true",
        help="Bypass daily dedup guard",
    )
    return parser.parse_args()


def already_completed_today(log_dir: Path, day_tag_str: str) -> bool:
    return latest_log_contains_sentinel(
        log_dir,
        f"check_burn_in_status_{day_tag_str}_*.log",
        COMPLETE_SENTINEL,
    )


def scan_artifacts(export_dir: Path, window_days: int, today: dt.date) -> list[dict[str, object]]:
    """Scan daily_paper_trading export artifacts within *window_days* of *today*.

    Returns a list of entry dicts sorted chronologically by date, one per
    calendar date (the most-recent artifact for that date is selected).
    """
    cutoff = today - dt.timedelta(days=window_days - 1)

    # Group filenames by date prefix; keep only those within the window.
    by_date: dict[str, list[str]] = {}
    if export_dir.is_dir():
        for path in export_dir.iterdir():
            m = _ARTIFACT_RE.match(path.name)
            if not m:
                continue
            date_str = m.group(1)  # YYYYMMDD
            try:
                file_date = dt.date(int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8]))
            except ValueError:
                continue
            if file_date < cutoff or file_date > today:
                continue
            by_date.setdefault(date_str, []).append(path.name)

    entries: list[dict[str, object]] = []
    for date_str, filenames in sorted(by_date.items()):
        # Use lexicographically latest filename (highest HHMMSS = most recent).
        chosen = sorted(filenames)[-1]
        artifact_path = export_dir / chosen
        try:
            data = json.loads(artifact_path.read_text(encoding="utf-8"))
        except OSError, json.JSONDecodeError:
            data = {}

        status = data.get("status", DAILY_RUN_STATUS_FAILED)
        entry: dict[str, object] = {
            "date": f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}",
            "status": status,
            "artifact_file": chosen,
        }
        if "failed_step" in data:
            entry["failed_step"] = data["failed_step"]
        entries.append(entry)

    return entries


def evaluate_readiness(
    entries: list[dict[str, object]],
    min_consecutive_days: int,
    max_failure_rate_pct: float,
) -> dict[str, object]:
    """Compute readiness metrics from sorted *entries*."""
    total_runs = len(entries)
    failed_runs = sum(1 for e in entries if e.get("status") != DAILY_RUN_STATUS_SUCCESS)
    failure_rate_pct = (failed_runs / total_runs * 100) if total_runs > 0 else 0.0

    # Count trailing consecutive successful entries.
    consecutive_successes = 0
    for entry in reversed(entries):
        if entry.get("status") == DAILY_RUN_STATUS_SUCCESS:
            consecutive_successes += 1
        else:
            break

    ready_for_live = consecutive_successes >= min_consecutive_days and failure_rate_pct <= max_failure_rate_pct

    return {
        "total_runs_in_window": total_runs,
        "consecutive_successes": consecutive_successes,
        "failed_runs": failed_runs,
        "failure_rate_pct": round(failure_rate_pct, 2),
        "ready_for_live": ready_for_live,
    }


def main() -> int:
    args = parse_args()

    repo_root = Path(args.repo_root).expanduser().resolve()
    logs_dir = logs_dir_for_repo(repo_root)
    artifacts_dir = repo_root / "local" / "artifacts"
    export_dir = repo_root / "local" / "exports" / "daily_paper_trading"

    logs_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    now = dt.datetime.now()
    today_tag = day_tag(now)

    # Dedup check BEFORE creating a new log file so the glob only matches
    # pre-existing sentinel logs, not a freshly created empty one.
    if not args.force_run and already_completed_today(logs_dir, today_tag):
        message = "Burn-in status check already completed today; skipping. Use --force-run to override."
        print(message)
        return 0

    timestamp = now.strftime("%Y%m%d_%H%M%S")
    log_path = logs_dir / f"check_burn_in_status_{today_tag}_{timestamp}.log"
    artifact_path = artifacts_dir / f"check_burn_in_status_{timestamp}.json"

    tee_line(log_path, f"[{ts()}] START: check_burn_in_status")

    entries = scan_artifacts(export_dir, args.window_days, now.date())
    metrics = evaluate_readiness(entries, args.min_consecutive_days, args.max_failure_rate_pct)

    artifact_payload: dict[str, object] = {
        "job": "check_burn_in_status",
        "generated_at": ts(),
        "window_days": args.window_days,
        "min_consecutive_days": args.min_consecutive_days,
        "max_failure_rate_pct": args.max_failure_rate_pct,
        **metrics,
        "entries": entries,
    }
    write_artifact(artifact_path, artifact_payload)

    summary = (
        f"BURN-IN STATUS: consecutive_successes={metrics['consecutive_successes']}"
        f"/{args.min_consecutive_days} required, "
        f"failure_rate={metrics['failure_rate_pct']}% "
        f"(limit {args.max_failure_rate_pct}%), "
        f"ready_for_live={metrics['ready_for_live']}"
    )
    tee_line(log_path, f"[{ts()}] {summary}")
    tee_line(log_path, f"[{ts()}] {COMPLETE_SENTINEL}")
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
