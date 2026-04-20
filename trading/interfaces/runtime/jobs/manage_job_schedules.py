#!/usr/bin/env python3
"""Manage job schedules on Windows or Linux."""

from __future__ import annotations

import argparse
import sys

from common.repo_paths import get_repo_root
from trading.interfaces.runtime.jobs.scheduler_installer import (
    ScheduledTaskSpec,
    register_tasks_for_platform,
    unregister_tasks_for_platform,
)

DAILY_PAPER_TRADING_MODULE = "trading.interfaces.runtime.jobs.daily_paper_trading"
DAILY_SNAPSHOT_MODULE = "trading.interfaces.runtime.jobs.daily_snapshot"
DAILY_BACKTEST_REFRESH_MODULE = "trading.interfaces.runtime.jobs.daily_backtest_refresh"
DAILY_TRADER_HEALTH_CHECK_MODULE = "trading.interfaces.runtime.jobs.check_daily_trader_health"
WEEKLY_DB_BACKUP_MODULE = "trading.interfaces.runtime.jobs.weekly_db_backup"

DEFAULT_DAILY_PAPER_TRADING_TASK_NAME = r"Trading\DailyPaperTrading"
DEFAULT_DAILY_PAPER_TRADING_FALLBACK_TASK_NAME = r"Trading\DailyPaperTradingFallback"
DEFAULT_DAILY_SNAPSHOT_TASK_NAME = r"Trading\DailySnapshot"
DEFAULT_DAILY_BACKTEST_REFRESH_TASK_NAME = r"Trading\DailyBacktestRefresh"
DEFAULT_DAILY_TRADER_HEALTH_CHECK_TASK_NAME = r"Trading\DailyTraderHealthCheck"
DEFAULT_WEEKLY_DB_BACKUP_TASK_NAME = r"Trading\WeeklyDbBackup"


def _scheduled_task(
    *,
    task_name: str,
    module: str,
    time: str,
    log_name: str,
    args: tuple[str, ...] = (),
    schedule_kind: str = "daily",
    day_of_week: str | None = None,
) -> ScheduledTaskSpec:
    return ScheduledTaskSpec(
        task_name=task_name,
        module=module,
        time=time,
        schedule_kind=schedule_kind,
        day_of_week=day_of_week,
        args=args,
        log_name=log_name,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Manage job schedules for paper trading operations."
    )
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
        "--daily-paper-trading-fallback-time",
        default="",
        help="Optional HH:MM for a second duplicate-guarded paper-trading attempt",
    )
    parser.add_argument(
        "--daily-paper-trading-fallback-task-name",
        default=DEFAULT_DAILY_PAPER_TRADING_FALLBACK_TASK_NAME,
    )
    parser.add_argument(
        "--daily-snapshot-time",
        default="",
        help="Optional HH:MM for the daily snapshot scheduler entry",
    )
    parser.add_argument(
        "--daily-snapshot-task-name",
        default=DEFAULT_DAILY_SNAPSHOT_TASK_NAME,
    )
    parser.add_argument(
        "--enable-daily-snapshot",
        action="store_true",
        help="Append --enable-run to the daily snapshot scheduler command",
    )
    parser.add_argument(
        "--daily-backtest-refresh-time",
        default="",
        help="Optional HH:MM for the daily backtest refresh entry",
    )
    parser.add_argument(
        "--daily-backtest-refresh-task-name",
        default=DEFAULT_DAILY_BACKTEST_REFRESH_TASK_NAME,
    )
    parser.add_argument(
        "--enable-daily-backtest-refresh",
        action="store_true",
        help="Append --enable-run to the daily backtest refresh command",
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
    parser.add_argument("--python", default=sys.executable, help="Python executable used by scheduler")
    return parser.parse_args()


def build_scheduled_tasks(args: argparse.Namespace) -> list[ScheduledTaskSpec]:
    tasks: list[ScheduledTaskSpec] = []

    if args.daily_paper_trading_time:
        tasks.append(
            _scheduled_task(
                task_name=args.daily_paper_trading_task_name,
                module=DAILY_PAPER_TRADING_MODULE,
                time=args.daily_paper_trading_time,
                log_name="daily_paper_trading_scheduler.log",
            )
        )

    if args.daily_paper_trading_fallback_time:
        tasks.append(
            _scheduled_task(
                task_name=args.daily_paper_trading_fallback_task_name,
                module=DAILY_PAPER_TRADING_MODULE,
                time=args.daily_paper_trading_fallback_time,
                args=("--run-source", "scheduled-daily-fallback"),
                log_name="daily_paper_trading_fallback_scheduler.log",
            )
        )

    if args.daily_snapshot_time:
        snapshot_args = ("--enable-run",) if args.enable_daily_snapshot else ()
        tasks.append(
            _scheduled_task(
                task_name=args.daily_snapshot_task_name,
                module=DAILY_SNAPSHOT_MODULE,
                time=args.daily_snapshot_time,
                args=snapshot_args,
                log_name="daily_snapshot_scheduler.log",
            )
        )

    if args.daily_backtest_refresh_time:
        refresh_args = ("--enable-run",) if args.enable_daily_backtest_refresh else ()
        tasks.append(
            _scheduled_task(
                task_name=args.daily_backtest_refresh_task_name,
                module=DAILY_BACKTEST_REFRESH_MODULE,
                time=args.daily_backtest_refresh_time,
                args=refresh_args,
                log_name="daily_backtest_refresh_scheduler.log",
            )
        )

    if args.health_check_time:
        tasks.append(
            _scheduled_task(
                task_name=args.health_check_task_name,
                module=DAILY_TRADER_HEALTH_CHECK_MODULE,
                time=args.health_check_time,
                args=("--max-age-hours", str(args.health_check_max_age_hours)),
                log_name="daily_trader_health_check_scheduler.log",
            )
        )

    if args.weekly_db_backup_time:
        tasks.append(
            _scheduled_task(
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
        args.daily_paper_trading_fallback_task_name,
        args.daily_snapshot_task_name,
        args.daily_backtest_refresh_task_name,
        args.health_check_task_name,
        args.weekly_db_backup_task_name,
    ]


def main() -> int:
    args = parse_args()
    if args.health_check_max_age_hours <= 0:
        print("--health-check-max-age-hours must be > 0", file=sys.stderr)
        return 2

    repo_root = get_repo_root(__file__)

    try:
        if args.unregister:
            code = unregister_tasks_for_platform(
                default_task_names(args),
                dry_run=args.dry_run,
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
