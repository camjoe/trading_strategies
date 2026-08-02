#!/usr/bin/env python3
"""Shared helpers for registering runtime jobs with cron, Task Scheduler, or systemd."""

from __future__ import annotations

import getpass
import platform
import re
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

SYSTEMD_CALENDAR_DAYS = {
    "monday": "Mon",
    "tuesday": "Tue",
    "wednesday": "Wed",
    "thursday": "Thu",
    "friday": "Fri",
    "saturday": "Sat",
    "sunday": "Sun",
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


def _systemd_available() -> bool:
    """Return True if systemd is the active init system."""
    return Path("/run/systemd/system").exists()


def _task_name_to_unit_name(task_name: str) -> str:
    """Convert 'Trading\\DailyPaperTrading' to 'daily-paper-trading'.

    The ``Trading\\`` prefix is dropped, so no unit name carries it — filtering
    installed timers on "trading" finds only the daily run and misses the rest.
    """
    name = task_name.split("\\")[-1]
    name = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "-", name)
    return name.lower()


def _systemd_calendar_expression(task: ScheduledTaskSpec) -> str:
    """Build a systemd OnCalendar expression from a task spec."""
    hour, minute = validate_time(task.time)
    if task.schedule_kind == "weekly":
        if task.day_of_week is None:
            raise ValueError(f"Weekly task '{task.task_name}' requires day_of_week")
        day_abbr = SYSTEMD_CALENDAR_DAYS[validate_day(task.day_of_week)]
        return f"{day_abbr} *-*-* {hour:02d}:{minute:02d}:00"
    return f"*-*-* {hour:02d}:{minute:02d}:00"


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
        f"{schedule_expr} cd {shlex.quote(str(repo_root))} && {command} >> {shlex.quote(str(log_path))} 2>&1 {marker}"
    )


def build_systemd_timer_unit(task: ScheduledTaskSpec, *, wake_system: bool = True) -> str:
    """Build the content of a systemd .timer unit file for a scheduled task."""
    calendar = _systemd_calendar_expression(task)
    wake_value = "yes" if wake_system else "no"
    return (
        "[Unit]\n"
        f"Description={task.task_name} timer\n"
        "\n"
        "[Timer]\n"
        f"OnCalendar={calendar}\n"
        f"WakeSystem={wake_value}\n"
        "Persistent=true\n"
        "\n"
        "[Install]\n"
        "WantedBy=timers.target\n"
    )


def build_systemd_service_unit(
    task: ScheduledTaskSpec,
    repo_root: Path,
    python_exe: Path,
    *,
    user: str,
    log_path: Path,
    env_file: Path | None = None,
) -> str:
    """Build the content of a systemd .service unit file for a scheduled task."""
    command_parts = [str(python_exe), "-m", task.module, *task.args]
    exec_start = " ".join(shlex.quote(part) for part in command_parts)
    env_line = f"EnvironmentFile=-{env_file}\n" if env_file else ""
    return (
        "[Unit]\n"
        f"Description={task.task_name} service\n"
        "\n"
        "[Service]\n"
        "Type=oneshot\n"
        f"User={user}\n"
        f"{env_line}"
        f"WorkingDirectory={repo_root}\n"
        f"ExecStart={exec_start}\n"
        f"StandardOutput=append:{log_path}\n"
        f"StandardError=append:{log_path}\n"
    )


def generate_systemd_install_script(
    tasks: Sequence[ScheduledTaskSpec],
    *,
    repo_root: Path,
    python_exe: Path,
    user: str,
    wake_system: bool,
    dry_run: bool,
    env_file: Path | None = None,
) -> int:
    """Generate a bash script that installs systemd timer and service units.

    In dry-run mode prints the unit file contents and commands without writing anything.
    Otherwise writes the script to local/install_trading_timers.sh and prints instructions.
    """
    from trading.interfaces.runtime.jobs.job_helpers import logs_dir_for_repo

    unit_dir = Path("/etc/systemd/system")
    log_dir = logs_dir_for_repo(repo_root)

    unit_files: dict[str, str] = {}
    timer_unit_names: list[str] = []

    for task in tasks:
        unit_name = _task_name_to_unit_name(task.task_name)
        log_path = log_dir / task.log_name
        unit_files[f"{unit_name}.service"] = build_systemd_service_unit(
            task, repo_root, python_exe, user=user, log_path=log_path, env_file=env_file
        )
        unit_files[f"{unit_name}.timer"] = build_systemd_timer_unit(task, wake_system=wake_system)
        timer_unit_names.append(f"{unit_name}.timer")

    if dry_run:
        print("DRY RUN: would create the following systemd unit files:\n")
        for filename, content in unit_files.items():
            print(f"--- {unit_dir / filename} ---")
            print(content)
        print("DRY RUN: would run:")
        print(f"  mkdir -p {log_dir}")
        print("  systemctl daemon-reload")
        for timer in timer_unit_names:
            print(f"  systemctl enable --now {timer}")
        return 0

    script_lines = [
        "#!/bin/bash",
        "set -euo pipefail",
        "",
        f"# Create log directory owned by {user}",
        f"mkdir -p {shlex.quote(str(log_dir))}",
        f"chown {shlex.quote(user)} {shlex.quote(str(log_dir))}",
        "",
    ]
    for filename, content in unit_files.items():
        target = unit_dir / filename
        script_lines.append(f"# Install {filename}")
        script_lines.append(f"cat > {shlex.quote(str(target))} << 'UNIT_EOF'")
        script_lines.append(content.rstrip())
        script_lines.append("UNIT_EOF")
        script_lines.append("")
    script_lines += [
        "systemctl daemon-reload",
    ]
    for timer in timer_unit_names:
        script_lines.append(f"systemctl enable --now {shlex.quote(timer)}")
    # List exactly the units this script enabled rather than filtering by name:
    # unit names drop the `Trading\` prefix, so a "trading" filter would report
    # only the daily run and quietly omit every other timer just installed.
    listed_timers = " ".join(shlex.quote(timer) for timer in timer_unit_names)
    script_lines += [
        "",
        'echo ""',
        'echo "Trading job timers installed:"',
        f"systemctl list-timers --all {listed_timers} || true",
    ]

    script_path = repo_root / "local" / "install_trading_timers.sh"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text("\n".join(script_lines) + "\n")
    script_path.chmod(0o755)

    print(f"Install script written to: {script_path}")
    print("\nRun the following to install the systemd timers (requires sudo):")
    print(f"  sudo bash {script_path}")
    return 0


def generate_systemd_uninstall_script(
    task_names: Sequence[str],
    *,
    repo_root: Path,
    dry_run: bool,
) -> int:
    """Generate a bash script that removes systemd timer and service units."""
    unit_dir = Path("/etc/systemd/system")
    timer_unit_names = [f"{_task_name_to_unit_name(n)}.timer" for n in task_names]
    service_unit_names = [f"{_task_name_to_unit_name(n)}.service" for n in task_names]

    if dry_run:
        print("DRY RUN: would run:")
        for timer in timer_unit_names:
            print(f"  systemctl disable --now {timer}")
        for name in timer_unit_names + service_unit_names:
            print(f"  rm -f /etc/systemd/system/{name}")
        print("  systemctl daemon-reload")
        return 0

    script_lines = ["#!/bin/bash", "set -euo pipefail", ""]
    for timer in timer_unit_names:
        script_lines.append(f"systemctl disable --now {shlex.quote(timer)} 2>/dev/null || true")
    script_lines.append("")
    for name in timer_unit_names + service_unit_names:
        script_lines.append(f"rm -f {shlex.quote(str(unit_dir / name))}")
    script_lines += [
        "",
        "systemctl daemon-reload",
        'echo "Trading job timers removed."',
    ]

    script_path = repo_root / "local" / "uninstall_trading_timers.sh"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text("\n".join(script_lines) + "\n")
    script_path.chmod(0o755)

    print(f"Uninstall script written to: {script_path}")
    print("\nRun the following to remove the systemd timers (requires sudo):")
    print(f"  sudo bash {script_path}")
    return 0


def register_tasks_for_platform(
    tasks: Sequence[ScheduledTaskSpec],
    *,
    repo_root: Path,
    python_exe: str | Path,
    dry_run: bool,
    scheduler_type: Literal["auto", "cron", "systemd"] = "auto",
    wake_system: bool = True,
    env_file: Path | None = None,
) -> int:
    resolved_system = platform.system().lower()
    resolved_repo_root = repo_root.expanduser().resolve()
    resolved_python = Path(python_exe).expanduser().absolute()

    if resolved_system == "windows":
        commands = [build_windows_register_command(task, resolved_repo_root, resolved_python) for task in tasks]
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

        use_systemd = scheduler_type == "systemd" or (scheduler_type == "auto" and _systemd_available())
        if use_systemd:
            return generate_systemd_install_script(
                tasks,
                repo_root=resolved_repo_root,
                python_exe=resolved_python,
                user=getpass.getuser(),
                wake_system=wake_system,
                dry_run=dry_run,
                env_file=env_file,
            )

        existing_lines = load_crontab_lines()
        updated_lines = list(existing_lines)
        for task in tasks:
            marker = f"# {task.task_name}"
            updated_lines = [line for line in updated_lines if marker not in line]
            log_path = logs_dir_for_repo(resolved_repo_root) / task.log_name
            updated_lines.append(build_linux_cron_line(task, resolved_repo_root, resolved_python, log_path))
        return write_crontab_lines(updated_lines, dry_run)

    raise RuntimeError(f"Unsupported OS for scheduler registration: {platform.system()}")


def unregister_tasks_for_platform(
    task_names: Sequence[str],
    *,
    dry_run: bool,
    scheduler_type: Literal["auto", "cron", "systemd"] = "auto",
    repo_root: Path | None = None,
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
        use_systemd = scheduler_type == "systemd" or (scheduler_type == "auto" and _systemd_available())
        if use_systemd:
            resolved_repo_root = (repo_root or Path.cwd()).expanduser().resolve()
            return generate_systemd_uninstall_script(task_names, repo_root=resolved_repo_root, dry_run=dry_run)

        updated_lines = list(load_crontab_lines())
        for task_name in task_names:
            marker = f"# {task_name}"
            updated_lines = [line for line in updated_lines if marker not in line]
        return write_crontab_lines(updated_lines, dry_run)

    raise RuntimeError(f"Unsupported OS for scheduler registration: {platform.system()}")
