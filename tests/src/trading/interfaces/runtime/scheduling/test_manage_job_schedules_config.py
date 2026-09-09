from __future__ import annotations

from pathlib import Path

import pytest

from tests.src.trading.interfaces.runtime.jobs.loaders import (
    make_manage_job_schedules_args,
    manage_job_schedules as module,
)
from trading.interfaces.runtime.scheduling.job_catalog import ScheduleResolution
from trading.interfaces.runtime.scheduling.scheduler_installer import ScheduledTaskSpec


@pytest.fixture
def _run_main_with_args(monkeypatch):
    def _run(**overrides):
        monkeypatch.setattr(module, "parse_args", lambda: make_manage_job_schedules_args(**overrides))
        return module.main()

    return _run


def _paper_spec() -> ScheduledTaskSpec:
    return ScheduledTaskSpec(
        task_name=r"Trading\DailyPaperTrading",
        module="trading.interfaces.runtime.jobs.daily.paper_trading",
        time="13:10",
    )


def test_apply_from_config_registers_enabled_and_removes_installed_stale(
    monkeypatch, tmp_path: Path, _run_main_with_args
) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(module, "get_repo_root", lambda _file: tmp_path)
    monkeypatch.setattr(
        module,
        "resolve_schedule_config",
        lambda _path: ScheduleResolution(
            to_register=[_paper_spec()],
            to_unregister=[r"Trading\WeeklyDbBackup", r"Trading\DailyTraderHealthCheck"],
        ),
    )
    # Only the backup is actually installed, so only it should be deleted.
    monkeypatch.setattr(module, "registered_task_names", lambda names, **_kwargs: {r"Trading\WeeklyDbBackup"})

    def fake_unregister(task_names, **_kwargs):
        captured["unregistered"] = list(task_names)
        return 0

    def fake_register(tasks, **_kwargs):
        captured["registered"] = [task.task_name for task in tasks]
        return 0

    monkeypatch.setattr(module, "unregister_tasks_for_platform", fake_unregister)
    monkeypatch.setattr(module, "register_tasks_for_platform", fake_register)

    assert _run_main_with_args(config="/cfg/job_schedule.json") == 0
    assert captured["unregistered"] == [r"Trading\WeeklyDbBackup"]
    assert captured["registered"] == [r"Trading\DailyPaperTrading"]


def test_apply_from_config_forwards_scheduler_options_and_env_file(
    monkeypatch, tmp_path: Path, _run_main_with_args
) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(module, "get_repo_root", lambda _file: tmp_path)
    monkeypatch.setattr(
        module, "resolve_schedule_config", lambda _path: ScheduleResolution(to_register=[_paper_spec()])
    )
    monkeypatch.setattr(module, "registered_task_names", lambda names, **_kwargs: set())

    def fake_register(tasks, *, scheduler_type, wake_system, env_file, **_kwargs):
        captured["scheduler_type"] = scheduler_type
        captured["wake_system"] = wake_system
        captured["env_file"] = env_file
        return 0

    monkeypatch.setattr(module, "register_tasks_for_platform", fake_register)

    assert (
        _run_main_with_args(
            config="/cfg/job_schedule.json", scheduler="systemd", wake_system=False, env_file="/etc/trading/.env"
        )
        == 0
    )
    assert captured["scheduler_type"] == "systemd"
    assert captured["wake_system"] is False
    assert captured["env_file"] == Path("/etc/trading/.env")


def test_apply_from_config_converts_empty_env_file_to_none(monkeypatch, tmp_path: Path, _run_main_with_args) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(module, "get_repo_root", lambda _file: tmp_path)
    monkeypatch.setattr(
        module, "resolve_schedule_config", lambda _path: ScheduleResolution(to_register=[_paper_spec()])
    )
    monkeypatch.setattr(module, "registered_task_names", lambda names, **_kwargs: set())

    def fake_register(tasks, *, env_file, **_kwargs):
        captured["env_file"] = env_file
        return 0

    monkeypatch.setattr(module, "register_tasks_for_platform", fake_register)

    assert _run_main_with_args(config="/cfg/job_schedule.json") == 0
    assert captured["env_file"] is None


def test_apply_from_config_reports_nonzero_scheduler_code(
    monkeypatch, tmp_path: Path, _run_main_with_args, capsys
) -> None:
    monkeypatch.setattr(module, "get_repo_root", lambda _file: tmp_path)
    monkeypatch.setattr(
        module, "resolve_schedule_config", lambda _path: ScheduleResolution(to_register=[_paper_spec()])
    )
    monkeypatch.setattr(module, "registered_task_names", lambda names, **_kwargs: set())
    monkeypatch.setattr(module, "register_tasks_for_platform", lambda *args, **kwargs: 4)

    assert _run_main_with_args(config="/cfg/job_schedule.json") == 4
    assert "Scheduler command returned a non-zero exit code." in capsys.readouterr().err


def test_apply_from_config_returns_error_for_bad_file(
    monkeypatch, tmp_path: Path, _run_main_with_args, capsys
) -> None:
    monkeypatch.setattr(module, "get_repo_root", lambda _file: tmp_path)
    monkeypatch.setattr(
        module,
        "resolve_schedule_config",
        lambda _path: (_ for _ in ()).throw(ValueError("bad config")),
    )

    assert _run_main_with_args(config="/cfg/job_schedule.json") == 1
    assert "Error: bad config" in capsys.readouterr().err


def test_status_reports_in_sync(monkeypatch, tmp_path: Path, _run_main_with_args, capsys) -> None:
    monkeypatch.setattr(module, "get_repo_root", lambda _file: tmp_path)
    monkeypatch.setattr(
        module, "resolve_schedule_config", lambda _path: ScheduleResolution(to_register=[_paper_spec()])
    )
    monkeypatch.setattr(module, "registered_task_names", lambda names, **_kwargs: {r"Trading\DailyPaperTrading"})

    assert _run_main_with_args(status=True) == 0
    assert "In sync." in capsys.readouterr().out


def test_status_reports_drift_when_enabled_job_missing(
    monkeypatch, tmp_path: Path, _run_main_with_args, capsys
) -> None:
    monkeypatch.setattr(module, "get_repo_root", lambda _file: tmp_path)
    monkeypatch.setattr(
        module, "resolve_schedule_config", lambda _path: ScheduleResolution(to_register=[_paper_spec()])
    )
    monkeypatch.setattr(module, "registered_task_names", lambda names, **_kwargs: set())

    assert _run_main_with_args(status=True) == 1
    out = capsys.readouterr().out
    assert "MISSING" in out
    assert "Drift found" in out


def test_status_returns_two_when_installed_state_unreadable(
    monkeypatch, tmp_path: Path, _run_main_with_args, capsys
) -> None:
    monkeypatch.setattr(module, "get_repo_root", lambda _file: tmp_path)
    monkeypatch.setattr(
        module, "resolve_schedule_config", lambda _path: ScheduleResolution(to_register=[_paper_spec()])
    )
    monkeypatch.setattr(module, "registered_task_names", lambda names, **_kwargs: None)

    assert _run_main_with_args(status=True) == 2
    assert "Cannot read installed schedules" in capsys.readouterr().err
