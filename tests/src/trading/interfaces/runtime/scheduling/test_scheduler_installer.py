from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from trading.interfaces.runtime.jobs import job_helpers
from trading.interfaces.runtime.scheduling import scheduler_installer


def test_validate_day_normalizes_valid_input() -> None:
    assert scheduler_installer.validate_day(" Monday ") == "monday"


def test_validate_day_rejects_unknown_day() -> None:
    with pytest.raises(ValueError, match="Invalid day 'Funday'"):
        scheduler_installer.validate_day("Funday")


@pytest.mark.parametrize("value", ["9", "9-10", "24:00", "12:60"])
def test_validate_time_rejects_invalid_values(value: str) -> None:
    with pytest.raises((ValueError, TypeError)):
        scheduler_installer.validate_time(value)


def test_schedule_expression_requires_day_for_weekly_task() -> None:
    task = scheduler_installer.ScheduledTaskSpec(
        task_name="weekly",
        module="pkg.mod",
        time="09:30",
        schedule_kind="weekly",
    )

    with pytest.raises(ValueError, match="requires day_of_week"):
        scheduler_installer._schedule_expression(task)


def test_load_crontab_lines_handles_missing_crontab(monkeypatch) -> None:
    monkeypatch.setattr(
        scheduler_installer.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stderr="no crontab for cam", stdout=""),
    )

    assert scheduler_installer.load_crontab_lines() == []


def test_load_crontab_lines_returns_existing_lines(monkeypatch) -> None:
    monkeypatch.setattr(
        scheduler_installer.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stderr="", stdout="line-one\nline-two\n"),
    )

    assert scheduler_installer.load_crontab_lines() == ["line-one", "line-two"]


def test_load_crontab_lines_raises_for_other_errors(monkeypatch) -> None:
    monkeypatch.setattr(
        scheduler_installer.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stderr="permission denied", stdout=""),
    )

    with pytest.raises(RuntimeError, match="permission denied"):
        scheduler_installer.load_crontab_lines()


def test_write_crontab_lines_dry_run_prints_content(capsys) -> None:
    assert scheduler_installer.write_crontab_lines(["0 1 * * * echo hi"], dry_run=True) == 0
    assert "would install crontab" in capsys.readouterr().out


def test_write_crontab_lines_passes_content_to_crontab(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_run(command: list[str], *, input: str, text: bool, check: bool) -> SimpleNamespace:
        captured["command"] = command
        captured["input"] = input
        captured["text"] = text
        captured["check"] = check
        return SimpleNamespace(returncode=7)

    monkeypatch.setattr(scheduler_installer.subprocess, "run", fake_run)

    exit_code = scheduler_installer.write_crontab_lines(["one", "two"], dry_run=False)

    assert exit_code == 7
    assert captured == {
        "command": ["crontab", "-"],
        "input": "one\ntwo\n",
        "text": True,
        "check": False,
    }


def test_build_windows_register_command_for_weekly_task(tmp_path: Path) -> None:
    task = scheduler_installer.ScheduledTaskSpec(
        task_name=r"Trading\WeeklyDbBackup",
        module="pkg.mod",
        time="09:30",
        schedule_kind="weekly",
        day_of_week="Sunday",
        args=("--flag", "value with space"),
    )

    command = scheduler_installer.build_windows_register_command(task, tmp_path, tmp_path / "python.exe")

    assert "Register-ScheduledTask" in command
    assert "-Weekly" in command
    assert "-DaysOfWeek Sunday" in command
    assert "value with space" in command


def test_build_linux_cron_line_for_weekly_task(tmp_path: Path) -> None:
    task = scheduler_installer.ScheduledTaskSpec(
        task_name=r"Trading\WeeklyDbBackup",
        module="pkg.mod",
        time="04:05",
        schedule_kind="weekly",
        day_of_week="Monday",
        args=("--label", "value with space"),
    )

    line = scheduler_installer.build_linux_cron_line(
        task,
        tmp_path,
        tmp_path / "python",
        tmp_path / "logs" / "weekly.log",
    )

    assert line.startswith("5 4 * * 1 ")
    assert "value with space" in line
    assert f"# {task.task_name}" in line


def test_register_tasks_for_platform_windows_dry_run_prints_commands(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.setattr(scheduler_installer.platform, "system", lambda: "Windows")

    exit_code = scheduler_installer.register_tasks_for_platform(
        [scheduler_installer.ScheduledTaskSpec(task_name="task", module="pkg.mod", time="09:30")],
        repo_root=tmp_path,
        python_exe=tmp_path / "python.exe",
        dry_run=True,
    )

    assert exit_code == 0
    assert "DRY RUN powershell command" in capsys.readouterr().out


def test_register_tasks_for_platform_windows_stops_on_first_nonzero(monkeypatch, tmp_path: Path) -> None:
    commands: list[list[str]] = []

    monkeypatch.setattr(scheduler_installer.platform, "system", lambda: "Windows")

    def fake_run(command: list[str], check: bool) -> SimpleNamespace:
        commands.append(command)
        return SimpleNamespace(returncode=9)

    monkeypatch.setattr(scheduler_installer.subprocess, "run", fake_run)

    exit_code = scheduler_installer.register_tasks_for_platform(
        [
            scheduler_installer.ScheduledTaskSpec(task_name="task-a", module="pkg.a", time="09:30"),
            scheduler_installer.ScheduledTaskSpec(task_name="task-b", module="pkg.b", time="10:30"),
        ],
        repo_root=tmp_path,
        python_exe=tmp_path / "python.exe",
        dry_run=False,
    )

    assert exit_code == 9
    assert len(commands) == 1
    assert commands[0][0:2] == ["powershell", "-Command"]


def test_register_tasks_for_platform_windows_returns_zero_when_all_commands_succeed(
    monkeypatch, tmp_path: Path
) -> None:
    commands: list[list[str]] = []
    monkeypatch.setattr(scheduler_installer.platform, "system", lambda: "Windows")

    def fake_run(command: list[str], check: bool) -> SimpleNamespace:
        commands.append(command)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(scheduler_installer.subprocess, "run", fake_run)

    exit_code = scheduler_installer.register_tasks_for_platform(
        [scheduler_installer.ScheduledTaskSpec(task_name="task-a", module="pkg.a", time="09:30")],
        repo_root=tmp_path,
        python_exe=tmp_path / "python.exe",
        dry_run=False,
    )

    assert exit_code == 0
    assert len(commands) == 1


def test_register_tasks_for_platform_linux_replaces_existing_entries(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}
    existing_line = "0 1 * * * old-command # Trading\\DailySnapshot"

    monkeypatch.setattr(scheduler_installer.platform, "system", lambda: "Linux")
    # Pin the systemd probe so the auto->cron fallback is deterministic on every
    # host (CI Linux has /run/systemd/system; a dev box may not).
    monkeypatch.setattr(scheduler_installer, "_systemd_available", lambda: False)
    monkeypatch.setattr(scheduler_installer, "load_crontab_lines", lambda: [existing_line, "keep-me"])
    monkeypatch.setattr(job_helpers, "logs_dir_for_repo", lambda repo_root: repo_root / "logs")

    def fake_write(lines: list[str], dry_run: bool) -> int:
        captured["lines"] = lines
        captured["dry_run"] = dry_run
        return 3

    monkeypatch.setattr(scheduler_installer, "write_crontab_lines", fake_write)

    exit_code = scheduler_installer.register_tasks_for_platform(
        [scheduler_installer.ScheduledTaskSpec(task_name=r"Trading\DailySnapshot", module="pkg.mod", time="09:30")],
        repo_root=tmp_path,
        python_exe=tmp_path / "python",
        dry_run=False,
    )

    assert exit_code == 3
    assert captured["dry_run"] is False
    assert "keep-me" in captured["lines"]
    assert existing_line not in captured["lines"]
    assert any("Trading\\DailySnapshot" in line for line in captured["lines"])


def test_register_tasks_for_platform_rejects_unsupported_os(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(scheduler_installer.platform, "system", lambda: "Darwin")

    with pytest.raises(RuntimeError, match="Unsupported OS"):
        scheduler_installer.register_tasks_for_platform([], repo_root=tmp_path, python_exe="python", dry_run=False)


def test_unregister_tasks_for_platform_windows_dry_run_prints_commands(monkeypatch, capsys) -> None:
    monkeypatch.setattr(scheduler_installer.platform, "system", lambda: "Windows")

    exit_code = scheduler_installer.unregister_tasks_for_platform([r"Trading\DailySnapshot"], dry_run=True)

    assert exit_code == 0
    assert "DRY RUN: schtasks /Delete /TN Trading\\DailySnapshot /F" in capsys.readouterr().out


def test_unregister_tasks_for_platform_windows_attempts_all_deletes(monkeypatch) -> None:
    commands: list[list[str]] = []
    results = iter([1, 0])

    monkeypatch.setattr(scheduler_installer.platform, "system", lambda: "Windows")

    def fake_run(command: list[str], check: bool) -> SimpleNamespace:
        commands.append(command)
        return SimpleNamespace(returncode=next(results))

    monkeypatch.setattr(scheduler_installer.subprocess, "run", fake_run)

    exit_code = scheduler_installer.unregister_tasks_for_platform(
        [r"Trading\MissingTask", r"Trading\ExistingTask"],
        dry_run=False,
    )

    assert commands == [
        ["schtasks", "/Delete", "/TN", r"Trading\MissingTask", "/F"],
        ["schtasks", "/Delete", "/TN", r"Trading\ExistingTask", "/F"],
    ]
    assert exit_code == 1


def test_unregister_tasks_for_platform_linux_removes_matching_entries(monkeypatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(scheduler_installer.platform, "system", lambda: "Linux")
    # Force the cron path regardless of whether the host runs systemd.
    monkeypatch.setattr(scheduler_installer, "_systemd_available", lambda: False)
    monkeypatch.setattr(
        scheduler_installer,
        "load_crontab_lines",
        lambda: ["keep", "0 1 * * * cmd # Trading\\DailySnapshot"],
    )

    def fake_write(lines: list[str], dry_run: bool) -> int:
        captured["lines"] = lines
        captured["dry_run"] = dry_run
        return 0

    monkeypatch.setattr(scheduler_installer, "write_crontab_lines", fake_write)

    exit_code = scheduler_installer.unregister_tasks_for_platform([r"Trading\DailySnapshot"], dry_run=True)

    assert exit_code == 0
    assert captured == {"lines": ["keep"], "dry_run": True}


def test_unregister_tasks_for_platform_rejects_unsupported_os(monkeypatch) -> None:
    monkeypatch.setattr(scheduler_installer.platform, "system", lambda: "Darwin")

    with pytest.raises(RuntimeError, match="Unsupported OS"):
        scheduler_installer.unregister_tasks_for_platform(["task"], dry_run=False)


# --- systemd backend ---------------------------------------------------------


def test_task_name_to_unit_name_kebab_cases_camelcase() -> None:
    assert scheduler_installer._task_name_to_unit_name(r"Trading\DailyPaperTrading") == "daily-paper-trading"
    assert scheduler_installer._task_name_to_unit_name(r"Trading\WeeklyDbBackup") == "weekly-db-backup"


@pytest.mark.parametrize(
    ("day", "cron_field", "systemd_abbr"),
    [
        ("Monday", "1", "Mon"),
        ("Tuesday", "2", "Tue"),
        ("Wednesday", "3", "Wed"),
        ("Thursday", "4", "Thu"),
        ("Friday", "5", "Fri"),
        ("Saturday", "6", "Sat"),
        # cron numbers Sunday 0, not 7.
        ("Sunday", "0", "Sun"),
    ],
)
def test_every_day_renders_for_cron_and_systemd(day: str, cron_field: str, systemd_abbr: str, tmp_path: Path) -> None:
    task = scheduler_installer.ScheduledTaskSpec(
        task_name="t", module="pkg.mod", time="04:05", schedule_kind="weekly", day_of_week=day
    )

    cron_line = scheduler_installer.build_linux_cron_line(task, tmp_path, tmp_path / "python", tmp_path / "job.log")
    assert cron_line.startswith(f"5 4 * * {cron_field} ")
    assert scheduler_installer._systemd_calendar_expression(task) == f"{systemd_abbr} *-*-* 04:05:00"


def test_systemd_calendar_expression_for_daily_and_weekly() -> None:
    daily = scheduler_installer.ScheduledTaskSpec(task_name="t", module="pkg.mod", time="13:05")
    weekly = scheduler_installer.ScheduledTaskSpec(
        task_name="t", module="pkg.mod", time="12:58", schedule_kind="weekly", day_of_week="Sunday"
    )

    assert scheduler_installer._systemd_calendar_expression(daily) == "*-*-* 13:05:00"
    assert scheduler_installer._systemd_calendar_expression(weekly) == "Sun *-*-* 12:58:00"


def test_build_systemd_timer_unit_sets_wake_system() -> None:
    task = scheduler_installer.ScheduledTaskSpec(
        task_name=r"Trading\WeeklyDbBackup",
        module="pkg.mod",
        time="12:58",
        schedule_kind="weekly",
        day_of_week="Sunday",
    )

    enabled = scheduler_installer.build_systemd_timer_unit(task, wake_system=True)
    assert "OnCalendar=Sun *-*-* 12:58:00" in enabled
    assert "WakeSystem=yes" in enabled
    assert "Persistent=true" in enabled
    assert "WantedBy=timers.target" in enabled

    disabled = scheduler_installer.build_systemd_timer_unit(task, wake_system=False)
    assert "WakeSystem=no" in disabled


def test_build_systemd_service_unit_includes_user_command_and_optional_env_file(tmp_path: Path) -> None:
    task = scheduler_installer.ScheduledTaskSpec(
        task_name=r"Trading\DailyPaperTrading",
        module="pkg.mod",
        time="13:00",
        args=("--run-source", "scheduled-daily"),
    )
    log_path = tmp_path / "logs" / "daily.log"

    without_env = scheduler_installer.build_systemd_service_unit(
        task, tmp_path, tmp_path / "python", user="cam", log_path=log_path
    )
    assert "Type=oneshot" in without_env
    assert "User=cam" in without_env
    assert "-m pkg.mod --run-source scheduled-daily" in without_env
    assert f"StandardOutput=append:{log_path}" in without_env
    assert "EnvironmentFile" not in without_env

    with_env = scheduler_installer.build_systemd_service_unit(
        task, tmp_path, tmp_path / "python", user="cam", log_path=log_path, env_file=tmp_path / ".env"
    )
    # The '-' prefix makes a missing env file non-fatal to the job.
    assert f"EnvironmentFile=-{tmp_path / '.env'}" in with_env


def test_generate_systemd_install_script_dry_run_prints_units(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.setattr(job_helpers, "logs_dir_for_repo", lambda repo_root: repo_root / "logs")
    task = scheduler_installer.ScheduledTaskSpec(
        task_name=r"Trading\DailyPaperTrading", module="pkg.mod", time="13:00"
    )

    exit_code = scheduler_installer.generate_systemd_install_script(
        [task], repo_root=tmp_path, python_exe=tmp_path / "python", user="cam", wake_system=True, dry_run=True
    )

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "daily-paper-trading.service" in out
    assert "daily-paper-trading.timer" in out
    assert "systemctl enable --now daily-paper-trading.timer" in out
    assert not (tmp_path / "local" / "install_trading_timers.sh").exists()


def test_generate_systemd_install_script_writes_executable_script(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.setattr(job_helpers, "logs_dir_for_repo", lambda repo_root: repo_root / "logs")
    task = scheduler_installer.ScheduledTaskSpec(
        task_name=r"Trading\WeeklyDbBackup",
        module="pkg.mod",
        time="12:58",
        schedule_kind="weekly",
        day_of_week="Sunday",
    )

    exit_code = scheduler_installer.generate_systemd_install_script(
        [task], repo_root=tmp_path, python_exe=tmp_path / "python", user="cam", wake_system=True, dry_run=False
    )

    script_path = tmp_path / "local" / "install_trading_timers.sh"
    assert exit_code == 0
    assert script_path.exists()
    body = script_path.read_text()
    assert body.startswith("#!/bin/bash")
    assert "weekly-db-backup.service" in body
    assert "systemctl enable --now weekly-db-backup.timer" in body
    assert f"sudo bash {script_path}" in capsys.readouterr().out


def test_generate_systemd_uninstall_script_writes_disable_and_remove_steps(tmp_path: Path) -> None:
    exit_code = scheduler_installer.generate_systemd_uninstall_script(
        [r"Trading\DailyPaperTrading"], repo_root=tmp_path, dry_run=False
    )

    script_path = tmp_path / "local" / "uninstall_trading_timers.sh"
    assert exit_code == 0
    body = script_path.read_text()
    # shlex.quote leaves simple unit names unquoted; assert on names (paths render
    # platform-specifically, so this test stays valid when run on Windows).
    assert "systemctl disable --now daily-paper-trading.timer" in body
    assert "daily-paper-trading.timer" in body
    assert "daily-paper-trading.service" in body


def test_register_tasks_for_platform_linux_uses_systemd_when_available(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.setattr(scheduler_installer.platform, "system", lambda: "Linux")
    monkeypatch.setattr(scheduler_installer, "_systemd_available", lambda: True)
    monkeypatch.setattr(scheduler_installer.getpass, "getuser", lambda: "cam")
    monkeypatch.setattr(job_helpers, "logs_dir_for_repo", lambda repo_root: repo_root / "logs")

    exit_code = scheduler_installer.register_tasks_for_platform(
        [
            scheduler_installer.ScheduledTaskSpec(
                task_name=r"Trading\DailyPaperTrading", module="pkg.mod", time="13:00"
            )
        ],
        repo_root=tmp_path,
        python_exe=tmp_path / "python",
        dry_run=True,
    )

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "would create the following systemd unit files" in out
    assert "WakeSystem=yes" in out


def test_register_tasks_for_platform_linux_scheduler_cron_overrides_systemd(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(scheduler_installer.platform, "system", lambda: "Linux")
    monkeypatch.setattr(scheduler_installer, "_systemd_available", lambda: True)
    monkeypatch.setattr(scheduler_installer, "load_crontab_lines", lambda: [])
    monkeypatch.setattr(job_helpers, "logs_dir_for_repo", lambda repo_root: repo_root / "logs")

    def fake_write(lines: list[str], dry_run: bool) -> int:
        captured["lines"] = lines
        return 0

    monkeypatch.setattr(scheduler_installer, "write_crontab_lines", fake_write)

    exit_code = scheduler_installer.register_tasks_for_platform(
        [scheduler_installer.ScheduledTaskSpec(task_name=r"Trading\DailySnapshot", module="pkg.mod", time="13:00")],
        repo_root=tmp_path,
        python_exe=tmp_path / "python",
        dry_run=False,
        scheduler_type="cron",
    )

    assert exit_code == 0
    assert any("Trading\\DailySnapshot" in line for line in captured["lines"])


def test_unregister_tasks_for_platform_linux_uses_systemd_when_available(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.setattr(scheduler_installer.platform, "system", lambda: "Linux")
    monkeypatch.setattr(scheduler_installer, "_systemd_available", lambda: True)

    exit_code = scheduler_installer.unregister_tasks_for_platform(
        [r"Trading\DailyPaperTrading"], dry_run=True, repo_root=tmp_path
    )

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "systemctl disable --now daily-paper-trading.timer" in out
