#!/usr/bin/env python3
"""Check the status of scheduled automation jobs (trading + backup).

Usage:
    python scripts/check_jobs.py
    python scripts/check_jobs.py --run-missing    # also trigger any jobs that haven't run
"""

from __future__ import annotations

import argparse
import datetime as dt
import subprocess
import sys
from pathlib import Path

from common.repo_paths import get_repo_root
from trading.interfaces.runtime.jobs.daily_backtest_refresh import COMPLETE_SENTINEL as DAILY_BACKTEST_REFRESH_SENTINEL
from trading.interfaces.runtime.jobs.daily_paper_trading import COMPLETE_SENTINEL as DAILY_SENTINEL
from trading.interfaces.runtime.jobs.daily_snapshot import COMPLETE_SENTINEL as DAILY_SNAPSHOT_SENTINEL
from trading.interfaces.runtime.jobs.job_helpers import logs_dir_for_repo
from trading.interfaces.runtime.jobs.weekly_db_backup import COMPLETE_SENTINEL as WEEKLY_SENTINEL

REPO_ROOT = get_repo_root(__file__)
LOGS_DIR = logs_dir_for_repo(REPO_ROOT)

DAILY_SCRIPT = "trading.interfaces.runtime.jobs.daily_paper_trading"
DAILY_SNAPSHOT_SCRIPT = "trading.interfaces.runtime.jobs.daily_snapshot"
DAILY_BACKTEST_REFRESH_SCRIPT = "trading.interfaces.runtime.jobs.daily_backtest_refresh"
WEEKLY_SCRIPT = "trading.interfaces.runtime.jobs.weekly_db_backup"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _log_has_sentinel(path: Path, sentinel: str) -> bool:
    try:
        return sentinel in path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False


def _log_mtime(path: Path) -> dt.datetime:
    return dt.datetime.fromtimestamp(path.stat().st_mtime, tz=dt.timezone.utc).astimezone()


def _days_ago(d: dt.date) -> str:
    delta = dt.date.today() - d
    if delta.days == 0:
        return "today"
    if delta.days == 1:
        return "yesterday"
    return f"{delta.days} days ago"


# ---------------------------------------------------------------------------
# Daily trading job
# ---------------------------------------------------------------------------

def _check_daily_job(
    *,
    job: str,
    pattern: str,
    sentinel: str,
    run_cmd: list[str],
) -> dict:
    """Return status dict for a daily job."""
    today = dt.date.today()
    logs = sorted(LOGS_DIR.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)

    today_str = today.strftime("%Y%m%d")
    today_complete = False
    today_log: Path | None = None
    for log in logs:
        if today_str in log.name:
            today_log = log
            today_complete = _log_has_sentinel(log, sentinel)
            break

    last_success: dt.date | None = None
    last_success_log: Path | None = None
    for log in logs:
        if _log_has_sentinel(log, DAILY_SENTINEL):
            last_success = _log_mtime(log).date()
            last_success_log = log
            break

    return {
        "job": job,
        "today_ran": today_log is not None,
        "today_complete": today_complete,
        "today_log": today_log,
        "last_success": last_success,
        "last_success_log": last_success_log,
        "run_cmd": run_cmd,
    }


def _check_daily() -> dict:
    """Return status dict for the daily paper-trading job."""
    return _check_daily_job(
        job="Daily Paper Trading",
        pattern="daily_paper_trading_[0-9]*_[0-9]*.log",
        sentinel=DAILY_SENTINEL,
        run_cmd=[sys.executable, "-m", DAILY_SCRIPT],
    )


def _check_daily_snapshot() -> dict:
    """Return status dict for the daily snapshot job."""
    return _check_daily_job(
        job="Daily Snapshot",
        pattern="daily_snapshot_[0-9]*_[0-9]*.log",
        sentinel=DAILY_SNAPSHOT_SENTINEL,
        run_cmd=[sys.executable, "-m", DAILY_SNAPSHOT_SCRIPT, "--enable-run"],
    )


def _check_daily_backtest_refresh() -> dict:
    """Return status dict for the daily backtest refresh job."""
    return _check_daily_job(
        job="Daily Backtest Refresh",
        pattern="daily_backtest_refresh_[0-9]*_[0-9]*.log",
        sentinel=DAILY_BACKTEST_REFRESH_SENTINEL,
        run_cmd=[sys.executable, "-m", DAILY_BACKTEST_REFRESH_SCRIPT, "--accounts", "all", "--enable-run"],
    )


# ---------------------------------------------------------------------------
# Weekly backup job
# ---------------------------------------------------------------------------

def _check_weekly() -> dict:
    """Return status dict for the weekly database backup job."""
    today = dt.date.today()
    iso = today.isocalendar()
    week_tag = f"{iso[0]}_W{iso[1]:02d}"

    pattern = "weekly_db_backup_*.log"
    logs = sorted(LOGS_DIR.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)

    this_week_complete = False
    this_week_log: Path | None = None
    for log in logs:
        if week_tag in log.name:
            this_week_log = log
            this_week_complete = _log_has_sentinel(log, WEEKLY_SENTINEL)
            break

    last_success: dt.date | None = None
    last_success_log: Path | None = None
    for log in logs:
        if _log_has_sentinel(log, WEEKLY_SENTINEL):
            last_success = _log_mtime(log).date()
            last_success_log = log
            break

    return {
        "job": "Weekly DB Backup",
        "week_tag": week_tag,
        "this_week_ran": this_week_log is not None,
        "this_week_complete": this_week_complete,
        "this_week_log": this_week_log,
        "last_success": last_success,
        "last_success_log": last_success_log,
        "run_cmd": [sys.executable, "-m", WEEKLY_SCRIPT],
    }


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

_OK = "✅"
_WARN = "⚠️ "
_ERR = "❌"


def _print_daily(s: dict) -> bool:
    """Print daily status. Returns True if healthy."""
    today = dt.date.today()
    print(f"\n{'─' * 50}")
    print(f"  {s['job']}")
    print(f"{'─' * 50}")

    if s["today_complete"]:
        print(f"  {_OK}  Completed today ({today})")
    elif s["today_ran"]:
        log_name = s["today_log"].name if s["today_log"] else "?"
        print(f"  {_WARN} Started today but sentinel not found — may have failed")
        print(f"      Log: {log_name}")
    else:
        print(f"  {_ERR}  No run recorded for today ({today})")

    if s["last_success"]:
        ago = _days_ago(s["last_success"])
        log_name = s["last_success_log"].name if s["last_success_log"] else "?"
        print(f"  Last success : {s['last_success']}  ({ago})")
        print(f"  Log          : {log_name}")
    else:
        print("  Last success : never found in logs")

    healthy = s["today_complete"]
    if not healthy:
        cmd = " ".join(str(x) for x in s["run_cmd"])
        print(f"\n  Run manually : {cmd}")
    return healthy


def _print_weekly(s: dict) -> bool:
    """Print weekly status. Returns True if healthy."""
    print(f"\n{'─' * 50}")
    print(f"  {s['job']}  ({s['week_tag']})")
    print(f"{'─' * 50}")

    if s["this_week_complete"]:
        print(f"  {_OK}  Completed this week ({s['week_tag']})")
    elif s["this_week_ran"]:
        log_name = s["this_week_log"].name if s["this_week_log"] else "?"
        print(f"  {_WARN} Started this week but sentinel not found — may have failed")
        print(f"      Log: {log_name}")
    else:
        print(f"  {_ERR}  No run recorded for {s['week_tag']}")

    if s["last_success"]:
        ago = _days_ago(s["last_success"])
        log_name = s["last_success_log"].name if s["last_success_log"] else "?"
        print(f"  Last success : {s['last_success']}  ({ago})")
        print(f"  Log          : {log_name}")
    else:
        print("  Last success : never found in logs")

    healthy = s["this_week_complete"]
    if not healthy:
        cmd = " ".join(str(x) for x in s["run_cmd"])
        print(f"\n  Run manually : {cmd}")
    return healthy


# ---------------------------------------------------------------------------
# Optional run-missing
# ---------------------------------------------------------------------------

def _trigger(run_cmd: list[str], label: str) -> None:
    print(f"\n  ▶  Triggering {label}…")
    try:
        result = subprocess.run(run_cmd, cwd=str(REPO_ROOT), timeout=300)
    except subprocess.TimeoutExpired:
        print(f"  {_ERR}  {label} timed out after 300 seconds.")
        return
    if result.returncode == 0:
        print(f"  {_OK}  {label} completed successfully.")
    else:
        print(f"  {_ERR}  {label} exited with code {result.returncode}.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Check status of scheduled automation jobs.")
    parser.add_argument(
        "--run-missing",
        action="store_true",
        help="Trigger any jobs that haven't run successfully yet (daily or weekly).",
    )
    args = parser.parse_args()

    today = dt.date.today()
    print(f"\n{'=' * 50}")
    print(f"  Automation Job Status — {today}")
    print(f"{'=' * 50}")

    daily_jobs = [
        _check_daily(),
        _check_daily_snapshot(),
        _check_daily_backtest_refresh(),
    ]
    weekly = _check_weekly()

    daily_ok = True
    for daily in daily_jobs:
        daily_ok = _print_daily(daily) and daily_ok
    weekly_ok = _print_weekly(weekly)

    print(f"\n{'─' * 50}\n")

    if args.run_missing:
        for daily in daily_jobs:
            if not daily["today_complete"]:
                _trigger(daily["run_cmd"], daily["job"])
        if not weekly_ok:
            _trigger(weekly["run_cmd"], weekly["job"])
        daily_ok = all(
            (
                _check_daily()["today_complete"],
                _check_daily_snapshot()["today_complete"],
                _check_daily_backtest_refresh()["today_complete"],
            )
        )
        weekly_ok = _check_weekly()["this_week_complete"]
    else:
        if not daily_ok or not weekly_ok:
            print("  Tip: pass --run-missing to trigger any outstanding jobs.\n")

    return 0 if (daily_ok and weekly_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
