#!/usr/bin/env python3
"""Register/unregister weekly DB backup schedule on Windows or Linux."""

from __future__ import annotations

import argparse
import platform
import subprocess
import sys
from pathlib import Path

from common.repo_paths import get_repo_root

WINDOWS_DAYS = {
    "monday": "MON",
    "tuesday": "TUE",
    "wednesday": "WED",
    "thursday": "THU",
    "friday": "FRI",
    "saturday": "SAT",
    "sunday": "SUN",
}

CRON_DAYS = {
    "monday": 1,
    "tuesday": 2,
    "wednesday": 3,
    "thursday": 4,
    "friday": 5,
    "saturday": 6,
    "sunday": 0,
}

WEEKLY_BACKUP_MODULE = "trading.interfaces.runtime.jobs.weekly_db_backup"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Register weekly backup schedule.")
    parser.add_argument("--day-of-week", default="Sunday", help="Day to run backup (default: Sunday)")
    parser.add_argument("--time", default="02:00", help="24h time HH:MM (default: 02:00)")
    parser.add_argument("--task-name", default="TradingStrategies_WeeklyDbBackup")
    parser.add_argument("--unregister", action="store_true", help="Remove schedule entry")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without applying")
    parser.add_argument("--python", default=sys.executable, help="Python executable used by scheduler")
    return parser.parse_args()


def validate_day(day: str) -> str:
    key = day.strip().lower()
    if key not in WINDOWS_DAYS:
        allowed = ", ".join(name.title() for name in WINDOWS_DAYS)
        raise ValueError(f"Invalid day '{day}'. Use one of: {allowed}")
    return key


def validate_time(value: str) -> tuple[int, int]:
    parts = value.split(":")
    if len(parts) != 2:
        raise ValueError("Time must be HH:MM")
    hour, minute = int(parts[0]), int(parts[1])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("Time must be HH:MM in 24-hour format")
    return hour, minute


def windows_register(args: argparse.Namespace) -> int:
    day_key = validate_day(args.day_of_week)
    validate_time(args.time)
    task_command = f'"{Path(args.python).resolve()}" -m {WEEKLY_BACKUP_MODULE}'
    cmd = [
        "schtasks",
        "/Create",
        "/TN",
        args.task_name,
        "/SC",
        "WEEKLY",
        "/D",
        WINDOWS_DAYS[day_key],
        "/ST",
        args.time,
        "/TR",
        task_command,
        "/F",
    ]
    if args.dry_run:
        print("DRY RUN:", " ".join(cmd))
        return 0
    return subprocess.run(cmd, check=False).returncode


def windows_unregister(args: argparse.Namespace) -> int:
    cmd = ["schtasks", "/Delete", "/TN", args.task_name, "/F"]
    if args.dry_run:
        print("DRY RUN:", " ".join(cmd))
        return 0
    return subprocess.run(cmd, check=False).returncode


def load_crontab_lines() -> list[str]:
    result = subprocess.run(["crontab", "-l"], check=False, capture_output=True, text=True)
    if result.returncode != 0:
        stderr = (result.stderr or "").lower()
        if "no crontab" in stderr:
            return []
        raise RuntimeError(result.stderr.strip() or "Unable to read crontab")
    return result.stdout.splitlines()


def write_crontab_lines(lines: list[str], dry_run: bool) -> int:
    content = "\n".join(lines).rstrip() + "\n"
    if dry_run:
        print("DRY RUN: would install crontab:\n")
        print(content)
        return 0
    result = subprocess.run(["crontab", "-"], input=content, text=True, check=False)
    return result.returncode


def linux_register(args: argparse.Namespace, repo_root: Path) -> int:
    day_key = validate_day(args.day_of_week)
    hour, minute = validate_time(args.time)
    marker = f"# {args.task_name}"
    python_exe = str(Path(args.python).resolve())
    log_path = repo_root / "local" / "logs" / "weekly_db_backup_cron.log"
    cron_line = (
        f"{minute} {hour} * * {CRON_DAYS[day_key]} "
        f"cd {repo_root} && {python_exe} -m {WEEKLY_BACKUP_MODULE} >> {log_path} 2>&1 {marker}"
    )

    lines = [line for line in load_crontab_lines() if marker not in line]
    lines.append(cron_line)
    return write_crontab_lines(lines, args.dry_run)


def linux_unregister(args: argparse.Namespace) -> int:
    marker = f"# {args.task_name}"
    lines = [line for line in load_crontab_lines() if marker not in line]
    return write_crontab_lines(lines, args.dry_run)


def main() -> int:
    args = parse_args()

    repo_root = get_repo_root(__file__)

    system = platform.system().lower()
    try:
        if system == "windows":
            if args.unregister:
                code = windows_unregister(args)
            else:
                code = windows_register(args)
        elif system == "linux":
            if args.unregister:
                code = linux_unregister(args)
            else:
                code = linux_register(args, repo_root)
        else:
            print(f"Unsupported OS for scheduler registration: {platform.system()}", file=sys.stderr)
            return 2
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if code != 0:
        print("Scheduler command returned a non-zero exit code.", file=sys.stderr)
        return code

    action = "removed" if args.unregister else "registered"
    print(f"Weekly backup schedule '{args.task_name}' {action}.")
    if not args.unregister:
        print(f"Runs every {args.day_of_week} at {args.time}.")
        print(f"Repo: {repo_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
