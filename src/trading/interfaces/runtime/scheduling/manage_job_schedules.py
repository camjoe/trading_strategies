#!/usr/bin/env python3
"""Manage job schedules on Windows or Linux."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

from common.git import get_repo_root
from trading.interfaces.runtime.jobs.job_helpers import DAILY_CHALLENGER_SHADOW_EVAL_MODULE
from trading.interfaces.runtime.scheduling.scheduler_installer import (
    ScheduledTaskSpec,
    register_tasks_for_platform,
    unregister_tasks_for_platform,
)

DAILY_PAPER_TRADING_MODULE = "trading.interfaces.runtime.jobs.daily.paper_trading"
DAILY_TRADER_HEALTH_CHECK_MODULE = "trading.interfaces.runtime.jobs.daily.trader_health"
WEEKLY_DB_BACKUP_MODULE = "trading.interfaces.runtime.jobs.maintenance.weekly_db_backup"

DEFAULT_DAILY_PAPER_TRADING_TASK_NAME = r"Trading\DailyPaperTrading"
DEFAULT_DAILY_CHALLENGER_SHADOW_EVAL_TASK_NAME = r"Trading\DailyChallengerShadowEval"
DEFAULT_DAILY_TRADER_HEALTH_CHECK_TASK_NAME = r"Trading\DailyTraderHealthCheck"
DEFAULT_WEEKLY_DB_BACKUP_TASK_NAME = r"Trading\WeeklyDbBackup"

# Time format used by scheduler CLI for daily task registration.
SCHEDULE_TIME_FORMAT = "%H:%M"
# Number of minutes in a day for wrap-around validation.
MINUTES_PER_DAY = 24 * 60
# Default lead time to run shadow evaluation before daily paper trading.
DEFAULT_SHADOW_EVAL_LEAD_MINUTES = 20


def _default_python() -> str:
    """Return the venv python path when running inside a venv, else sys.executable."""
    if sys.prefix != sys.base_prefix:
        venv_python = Path(sys.prefix) / "bin" / "python"
        if venv_python.exists():
            return str(venv_python)
    return sys.executable


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage job schedules for paper trading operations.")
    parser.add_argument(
        "--daily-paper-trading-time",
        default="",
        help="24h time HH:MM for the primary paper-trading run",
    )
    parser.add_argument(
        "--daily-paper-trading-task-name",
        default=DEFAULT_DAILY_PAPER_TRADING_TASK_NAME,
    )
    parser.add_argument(
        "--daily-challenger-shadow-eval-time",
        default="",
        help="Optional HH:MM for the daily challenger shadow-evaluation entry",
    )
    parser.add_argument(
        "--daily-challenger-shadow-eval-task-name",
        default=DEFAULT_DAILY_CHALLENGER_SHADOW_EVAL_TASK_NAME,
    )
    parser.add_argument(
        "--enable-daily-challenger-shadow-eval",
        action="store_true",
        help="Append --enable-run to the challenger shadow-evaluation scheduler command",
    )
    parser.add_argument(
        "--auto-shadow-eval-from-daily-paper",
        action="store_true",
        help=(
            "Derive shadow-eval task time from --daily-paper-trading-time when "
            "--daily-challenger-shadow-eval-time is not provided."
        ),
    )
    parser.add_argument(
        "--shadow-eval-lead-minutes",
        type=int,
        default=DEFAULT_SHADOW_EVAL_LEAD_MINUTES,
        help=(f"Lead minutes for auto-derived shadow-eval schedule (default: {DEFAULT_SHADOW_EVAL_LEAD_MINUTES})."),
    )
    parser.add_argument(
        "--health-check-time",
        default="",
        help="Optional HH:MM for the daily trader health-check entry",
    )
    parser.add_argument(
        "--health-check-task-name",
        default=DEFAULT_DAILY_TRADER_HEALTH_CHECK_TASK_NAME,
    )
    parser.add_argument(
        "--health-check-max-age-hours",
        type=float,
        default=24.0,
        help="Max age threshold passed to the health-check command (default: 24)",
    )
    parser.add_argument(
        "--weekly-db-backup-time",
        default="",
        help="Optional HH:MM for the weekly database backup entry",
    )
    parser.add_argument(
        "--weekly-db-backup-day-of-week",
        default="Sunday",
        help="Day of week for the weekly database backup entry (default: Sunday)",
    )
    parser.add_argument(
        "--weekly-db-backup-task-name",
        default=DEFAULT_WEEKLY_DB_BACKUP_TASK_NAME,
    )
    parser.add_argument("--unregister", action="store_true", help="Remove schedule entries")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without applying")
    parser.add_argument(
        "--python",
        default=_default_python(),
        help="Python executable used by scheduler (default: auto-detected venv python)",
    )
    parser.add_argument(
        "--scheduler",
        choices=["auto", "cron", "systemd"],
        default="auto",
        help="Scheduler backend: 'auto' picks systemd on Linux if available, else cron (default: auto)",
    )
    parser.add_argument(
        "--wake-system",
        action="store_true",
        default=True,
        help="Configure systemd timers to wake the system from sleep (default: true)",
    )
    parser.add_argument(
        "--no-wake-system",
        action="store_false",
        dest="wake_system",
        help="Disable WakeSystem on systemd timers",
    )
    parser.add_argument(
        "--env-file",
        default="",
        help=(
            "Path to a .env file to inject into each systemd service unit via EnvironmentFile=. "
            "The file is treated as optional (missing file is not an error). "
            "Has no effect when using cron or Windows Task Scheduler."
        ),
    )
    return parser.parse_args()


def _derive_shadow_eval_time_from_daily_paper(
    daily_paper_time: str,
    *,
    lead_minutes: int,
) -> str:
    if lead_minutes <= 0 or lead_minutes >= MINUTES_PER_DAY:
        raise ValueError(f"--shadow-eval-lead-minutes must be > 0 and < {MINUTES_PER_DAY}")
    base = datetime.strptime(daily_paper_time, SCHEDULE_TIME_FORMAT)
    derived = base - timedelta(minutes=lead_minutes)
    return derived.strftime(SCHEDULE_TIME_FORMAT)


def build_scheduled_tasks(args: argparse.Namespace) -> list[ScheduledTaskSpec]:
    tasks: list[ScheduledTaskSpec] = []

    if args.daily_paper_trading_time:
        tasks.append(
            ScheduledTaskSpec(
                task_name=args.daily_paper_trading_task_name,
                module=DAILY_PAPER_TRADING_MODULE,
                time=args.daily_paper_trading_time,
                log_name="daily_paper_trading_scheduler.log",
            )
        )

    shadow_eval_time = args.daily_challenger_shadow_eval_time
    auto_shadow_eval = False
    should_auto_derive_shadow_eval = (
        not shadow_eval_time and bool(args.auto_shadow_eval_from_daily_paper) and bool(args.daily_paper_trading_time)
    )
    if should_auto_derive_shadow_eval:
        shadow_eval_time = _derive_shadow_eval_time_from_daily_paper(
            args.daily_paper_trading_time,
            lead_minutes=int(args.shadow_eval_lead_minutes),
        )
        auto_shadow_eval = True

    if shadow_eval_time:
        shadow_eval_args = ("--enable-run",) if args.enable_daily_challenger_shadow_eval or auto_shadow_eval else ()
        tasks.append(
            ScheduledTaskSpec(
                task_name=args.daily_challenger_shadow_eval_task_name,
                module=DAILY_CHALLENGER_SHADOW_EVAL_MODULE,
                time=shadow_eval_time,
                args=shadow_eval_args,
                log_name="daily_challenger_shadow_eval_scheduler.log",
            )
        )

    if args.health_check_time:
        tasks.append(
            ScheduledTaskSpec(
                task_name=args.health_check_task_name,
                module=DAILY_TRADER_HEALTH_CHECK_MODULE,
                time=args.health_check_time,
                args=("--max-age-hours", str(args.health_check_max_age_hours)),
                log_name="daily_trader_health_check_scheduler.log",
            )
        )

    if args.weekly_db_backup_time:
        tasks.append(
            ScheduledTaskSpec(
                task_name=args.weekly_db_backup_task_name,
                module=WEEKLY_DB_BACKUP_MODULE,
                time=args.weekly_db_backup_time,
                log_name="weekly_db_backup_scheduler.log",
                schedule_kind="weekly",
                day_of_week=args.weekly_db_backup_day_of_week,
            )
        )

    return tasks


def default_task_names(args: argparse.Namespace) -> list[str]:
    return [
        args.daily_paper_trading_task_name,
        args.daily_challenger_shadow_eval_task_name,
        args.health_check_task_name,
        args.weekly_db_backup_task_name,
    ]


def main() -> int:
    args = parse_args()
    if args.health_check_max_age_hours <= 0:
        print("--health-check-max-age-hours must be > 0", file=sys.stderr)
        return 2
    shadow_eval_lead_is_invalid = (
        args.shadow_eval_lead_minutes <= 0 or args.shadow_eval_lead_minutes >= MINUTES_PER_DAY
    )
    if shadow_eval_lead_is_invalid:
        print(f"--shadow-eval-lead-minutes must be > 0 and < {MINUTES_PER_DAY}", file=sys.stderr)
        return 2

    repo_root = get_repo_root(__file__)

    try:
        if args.unregister:
            code = unregister_tasks_for_platform(
                default_task_names(args),
                dry_run=args.dry_run,
                scheduler_type=args.scheduler,
                repo_root=repo_root,
            )
        else:
            tasks = build_scheduled_tasks(args)
            if not tasks:
                print(
                    "Provide at least one schedule time to register runtime jobs "
                    "(for example --daily-paper-trading-time 13:10).",
                    file=sys.stderr,
                )
                return 2
            code = register_tasks_for_platform(
                tasks,
                repo_root=repo_root,
                python_exe=args.python,
                dry_run=args.dry_run,
                scheduler_type=args.scheduler,
                wake_system=args.wake_system,
                env_file=Path(args.env_file) if args.env_file else None,
            )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if code != 0:
        print("Scheduler command returned a non-zero exit code.", file=sys.stderr)
        return code

    action = "removed" if args.unregister else "registered"
    print(f"Runtime job schedules {action}.")
    if not args.unregister:
        print(f"Repo: {repo_root}")
        print(f"Python: {args.python}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
