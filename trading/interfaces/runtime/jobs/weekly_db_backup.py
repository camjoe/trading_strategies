#!/usr/bin/env python3
"""Run a weekly DB backup with logging + duplicate-week guard."""

from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

from common.repo_paths import get_repo_root
from trading.interfaces.runtime.jobs.task_runs import ADMIN_MODULE, latest_log_contains_sentinel, logs_dir_for_repo, run_command, tee_line, ts

REPO_ROOT = get_repo_root(__file__)
LOGS_DIR = logs_dir_for_repo(REPO_ROOT)

COMPLETE_SENTINEL = "COMPLETE: Weekly database backup succeeded."


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run weekly database backup.")
    parser.add_argument("--backup-dir", default="", help="Optional backup destination directory or .db file path")
    parser.add_argument("--force-run", action="store_true", help="Allow duplicate same-week run")
    return parser.parse_args()


def week_tag(now: dt.datetime) -> str:
    iso_year, iso_week, _ = now.isocalendar()
    return f"{iso_year}_W{iso_week:02d}"


def already_completed_this_week(log_dir: Path, tag: str) -> bool:
    return latest_log_contains_sentinel(
        log_dir,
        f"weekly_db_backup_{tag}_*.log",
        COMPLETE_SENTINEL,
    )


def main() -> int:
    args = parse_args()

    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    now = dt.datetime.now()
    tag = week_tag(now)

    if not args.force_run and already_completed_this_week(LOGS_DIR, tag):
        print("Weekly database backup already completed this week; skipping. Use --force-run to override.")
        return 0

    timestamp = now.strftime("%Y%m%d_%H%M%S")
    log_path = LOGS_DIR / f"weekly_db_backup_{tag}_{timestamp}.log"
    tee_line(log_path, f"[{ts()}] RUN META: force={bool(args.force_run)}")

    cmd = ["-m", ADMIN_MODULE, "backup-db"]
    if args.backup_dir:
        cmd.append(args.backup_dir)

    exit_code, _ = run_command(log_path, "Database backup", cmd, REPO_ROOT)

    if exit_code != 0:
        return exit_code

    tee_line(log_path, f"[{ts()}] {COMPLETE_SENTINEL}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
