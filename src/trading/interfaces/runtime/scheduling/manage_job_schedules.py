#!/usr/bin/env python3
"""Manage job schedules on Windows or Linux from the declarative schedule config."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Literal

from common.git import get_repo_root
from common.paths import JOB_SCHEDULE_PATH
from trading.interfaces.runtime.scheduling.job_catalog import (
    ALL_TASK_NAMES,
    ScheduleResolution,
    resolve_schedule_config,
)
from trading.interfaces.runtime.scheduling.scheduler_installer import (
    register_tasks_for_platform,
    registered_task_names,
    unregister_tasks_for_platform,
)

SchedulerChoice = Literal["auto", "cron", "systemd"]


def _default_python() -> str:
    """Return the venv python path when running inside a venv, else sys.executable."""
    if sys.prefix != sys.base_prefix:
        venv_python = Path(sys.prefix) / "bin" / "python"
        if venv_python.exists():
            return str(venv_python)
    return sys.executable


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage runtime job schedules from the schedule config file.")
    parser.add_argument(
        "--config",
        default="",
        help=(
            "Path to the declarative job schedule JSON file (see "
            f"src/infrastructure/config/job_schedule.example.json). Defaults to {JOB_SCHEDULE_PATH}. "
            "The file is the source of truth: enabled jobs are registered and the rest removed."
        ),
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Report drift between the config file and the schedules registered on this host, then exit.",
    )
    parser.add_argument("--unregister", action="store_true", help="Remove every catalog schedule entry")
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
        help="Wake the system from sleep before each run (systemd WakeSystem / Windows WakeToRun; default: true)",
    )
    parser.add_argument(
        "--no-wake-system",
        action="store_false",
        dest="wake_system",
        help="Disable the wake-from-sleep setting on the registered tasks",
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


def _config_path(args: argparse.Namespace) -> Path:
    """Resolve the schedule config path, defaulting to the tracked-beside-example live file."""
    return Path(args.config) if args.config else JOB_SCHEDULE_PATH


def apply_schedule_config(
    resolution: ScheduleResolution,
    *,
    repo_root: Path,
    python_exe: str,
    dry_run: bool,
    scheduler_type: SchedulerChoice,
    wake_system: bool,
    env_file: Path | None,
) -> int:
    """Make the host match the config: remove disabled jobs, then register enabled ones.

    Only jobs actually registered are removed, so a fresh apply does not fail on a
    delete of a never-registered task.
    """
    installed = registered_task_names(resolution.to_unregister, scheduler_type=scheduler_type, repo_root=repo_root)
    if installed is None:
        stale = list(resolution.to_unregister)
    else:
        stale = [name for name in resolution.to_unregister if name in installed]
    if stale:
        code = unregister_tasks_for_platform(
            stale, dry_run=dry_run, scheduler_type=scheduler_type, repo_root=repo_root
        )
        if code != 0:
            return code
    if not resolution.to_register:
        return 0
    return register_tasks_for_platform(
        resolution.to_register,
        repo_root=repo_root,
        python_exe=python_exe,
        dry_run=dry_run,
        scheduler_type=scheduler_type,
        wake_system=wake_system,
        env_file=env_file,
    )


def run_status_report(config_path: Path, *, scheduler_type: SchedulerChoice, repo_root: Path) -> int:
    """Print config-vs-installed drift. Return 0 in sync, 1 on drift, 2 if not readable."""
    resolution = resolve_schedule_config(config_path)
    desired = {spec.task_name for spec in resolution.to_register}
    installed = registered_task_names(ALL_TASK_NAMES, scheduler_type=scheduler_type, repo_root=repo_root)
    if installed is None:
        print(
            "Cannot read installed schedules from this host (systemd target). "
            "Run --status on the runtime host itself.",
            file=sys.stderr,
        )
        return 2

    print(f"Schedule config: {config_path}")
    for name in ALL_TASK_NAMES:
        want = name in desired
        have = name in installed
        if want and have:
            state = "OK        (enabled, registered)"
        elif want and not have:
            state = "MISSING   (enabled, not registered)"
        elif have and not want:
            state = "STALE     (registered, should be off)"
        else:
            state = "off       (disabled, not registered)"
        print(f"  {state}  {name}")

    missing = desired - installed
    stale = installed - desired
    if not missing and not stale:
        print("In sync.")
        return 0
    print("Drift found. Run an apply to reconcile:")
    print(f"  python -m trading.interfaces.runtime.scheduling.manage_job_schedules --config {config_path}")
    return 1


def main() -> int:
    args = parse_args()
    repo_root = get_repo_root(__file__)

    if args.status:
        try:
            return run_status_report(_config_path(args), scheduler_type=args.scheduler, repo_root=repo_root)
        except (FileNotFoundError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

    if args.unregister:
        try:
            code = unregister_tasks_for_platform(
                list(ALL_TASK_NAMES),
                dry_run=args.dry_run,
                scheduler_type=args.scheduler,
                repo_root=repo_root,
            )
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        if code != 0:
            print("Scheduler command returned a non-zero exit code.", file=sys.stderr)
            return code
        print("Runtime job schedules removed.")
        return 0

    try:
        resolution = resolve_schedule_config(_config_path(args))
        code = apply_schedule_config(
            resolution,
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

    print("Runtime job schedules applied from config.")
    print(f"Config: {_config_path(args)}")
    print(f"Repo: {repo_root}")
    print(f"Python: {args.python}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
