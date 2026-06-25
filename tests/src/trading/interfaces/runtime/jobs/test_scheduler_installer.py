from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from trading.interfaces.runtime.jobs import job_helpers, scheduler_installer


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
