#!/usr/bin/env python3
"""Run a weekly DB backup with logging + duplicate-week guard."""

from __future__ import annotations

import argparse
import datetime as dt
import subprocess
import sys
from pathlib import Path

from common.repo_paths import get_repo_root

REPO_ROOT = get_repo_root(__file__)
LOGS_DIR = REPO_ROOT / "local" / "logs"

COMPLETE_SENTINEL = "COMPLETE: Weekly database backup succeeded."


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run weekly database backup.")
    parser.add_argument("--backup-dir", default="", help="Optional backup destination directory or .db file path")
    parser.add_argument("--force-run", action="store_true", help="Allow duplicate same-week run")
    return parser.parse_args()


def week_tag(now: dt.datetime) -> str:
    iso_year, iso_week, _ = now.isocalendar()
    return f"{iso_year}_W{iso_week:02d}"


def tee_line(log_path: Path, text: str) -> None:
    print(text)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(text + "\n")


def already_completed_this_week(log_dir: Path, tag: str) -> bool:
    logs = sorted(log_dir.glob(f"weekly_db_backup_{tag}_*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not logs:
        return False
    latest = logs[0]
    try:
        return COMPLETE_SENTINEL in latest.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False


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
    tee_line(log_path, f"[{dt.datetime.now(dt.timezone.utc).astimezone().isoformat()}] RUN META: force={bool(args.force_run)}")

    cmd = [sys.executable, "-m", "dev_tools.db_admin", "backup-db"]
    if args.backup_dir:
        cmd.append(args.backup_dir)

    tee_line(log_path, f"[{dt.datetime.now(dt.timezone.utc).astimezone().isoformat()}] START: Database backup")
    process = subprocess.Popen(
        cmd,
        cwd=str(REPO_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
    )
    assert process.stdout is not None
    for line in process.stdout:
        tee_line(log_path, line.rstrip("\n"))
    exit_code = process.wait()

    if exit_code != 0:
        tee_line(log_path, f"[{dt.datetime.now(dt.timezone.utc).astimezone().isoformat()}] ERROR: Database backup failed.")
        return exit_code

    tee_line(log_path, f"[{dt.datetime.now(dt.timezone.utc).astimezone().isoformat()}] DONE: Database backup")
    tee_line(log_path, f"[{dt.datetime.now(dt.timezone.utc).astimezone().isoformat()}] {COMPLETE_SENTINEL}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
