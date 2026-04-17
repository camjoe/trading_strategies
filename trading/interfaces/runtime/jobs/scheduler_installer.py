#!/usr/bin/env python3
"""Shared helpers for registering runtime jobs with cron or Task Scheduler."""

from __future__ import annotations

import platform
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Sequence

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

ScheduleKind = Literal["daily", "weekly"]


@dataclass(frozen=True)
class ScheduledTaskSpec:
    task_name: str
    module: str
    time: str
    schedule_kind: ScheduleKind = "daily"
    day_of_week: str | None = None
    args: tuple[str, ...] = ()
    log_name: str = "runtime_job_scheduler.log"


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


def _powershell_quote(value: str) -> str:
    return value.replace("'", "''")


def _schedule_expression(task: ScheduledTaskSpec) -> tuple[int, int, str | None]:
    hour, minute = validate_time(task.time)
    if task.schedule_kind == "weekly":
        if task.day_of_week is None:
            raise ValueError(f"Weekly task '{task.task_name}' requires day_of_week")
        return hour, minute, validate_day(task.day_of_week)
    return hour, minute, None

def build_windows_register_command(task: ScheduledTaskSpec, repo_root: Path, python_exe: Path) -> str:
    _schedule_expression(task)
    argument = subprocess.list2cmdline(["-m", task.module, *task.args])
    if task.schedule_kind == "weekly":
        assert task.day_of_week is not None
        trigger = (
            "New-ScheduledTaskTrigger -Weekly "
            f"-DaysOfWeek {validate_day(task.day_of_week).title()} "
            f"-At '{_powershell_quote(task.time)}'"
        )
    else:
        trigger = f"New-ScheduledTaskTrigger -Daily -At '{_powershell_quote(task.time)}'"

    action = (
        "New-ScheduledTaskAction "
        f"-Execute '{_powershell_quote(str(python_exe))}' "
        f"-Argument '{_powershell_quote(argument)}' "
        f"-WorkingDirectory '{_powershell_quote(str(repo_root))}'"
    )
    return (
        f"Register-ScheduledTask -TaskName '{_powershell_quote(task.task_name)}' -Force "
        f"-Action ({action}) "
        f"-Trigger ({trigger})"
    )


def build_linux_cron_line(task: ScheduledTaskSpec, repo_root: Path, python_exe: Path, log_path: Path) -> str:
    hour, minute, cron_day = _schedule_expression(task)
    schedule_expr = f"{minute} {hour} * * *" if cron_day is None else f"{minute} {hour} * * {CRON_DAYS[cron_day]}"
    command_parts = [str(python_exe), "-m", task.module, *task.args]
    command = " ".join(shlex.quote(part) for part in command_parts)
    marker = f"# {task.task_name}"
    return (
        f"{schedule_expr} cd {shlex.quote(str(repo_root))} && "
        f"{command} >> {shlex.quote(str(log_path))} 2>&1 {marker}"
    )


def register_tasks_for_platform(
    tasks: Sequence[ScheduledTaskSpec],
    *,
    repo_root: Path,
    python_exe: str | Path,
    dry_run: bool,
) -> int:
    resolved_system = platform.system().lower()
    resolved_repo_root = repo_root.expanduser().resolve()
    resolved_python = Path(python_exe).expanduser().resolve()

    if resolved_system == "windows":
        commands = [
            build_windows_register_command(task, resolved_repo_root, resolved_python)
            for task in tasks
        ]
        if dry_run:
            for command in commands:
                print("DRY RUN powershell command:")
                print(command)
            return 0
        for command in commands:
            result = subprocess.run(["powershell", "-Command", command], check=False)
            if result.returncode != 0:
                return result.returncode
        return 0

    if resolved_system == "linux":
        from trading.interfaces.runtime.jobs.job_helpers import logs_dir_for_repo

        existing_lines = load_crontab_lines()
        updated_lines = list(existing_lines)
        for task in tasks:
            marker = f"# {task.task_name}"
            updated_lines = [line for line in updated_lines if marker not in line]
            log_path = logs_dir_for_repo(resolved_repo_root) / task.log_name
            updated_lines.append(
                build_linux_cron_line(task, resolved_repo_root, resolved_python, log_path)
            )
        return write_crontab_lines(updated_lines, dry_run)

    raise RuntimeError(f"Unsupported OS for scheduler registration: {platform.system()}")


def unregister_tasks_for_platform(
    task_names: Sequence[str],
    *,
    dry_run: bool,
) -> int:
    resolved_system = platform.system().lower()

    if resolved_system == "windows":
        commands = [["schtasks", "/Delete", "/TN", task_name, "/F"] for task_name in task_names]
        if dry_run:
            for command in commands:
                print("DRY RUN:", " ".join(command))
            return 0
        exit_code = 0
        for command in commands:
            result = subprocess.run(command, check=False)
            if result.returncode != 0:
                exit_code = result.returncode
        return exit_code

    if resolved_system == "linux":
        updated_lines = list(load_crontab_lines())
        for task_name in task_names:
            marker = f"# {task_name}"
            updated_lines = [line for line in updated_lines if marker not in line]
        return write_crontab_lines(updated_lines, dry_run)

    raise RuntimeError(f"Unsupported OS for scheduler registration: {platform.system()}")
