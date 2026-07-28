from __future__ import annotations

import sys
from pathlib import Path

import pytest

from tests.src.trading.interfaces.helpers import run_module_as_main
from tests.src.trading.interfaces.runtime.jobs.loaders import (
    make_manage_job_schedules_args,
    manage_job_schedules as module,
)


@pytest.fixture
def _run_main_with_args(monkeypatch):
    def _run(**overrides):
        monkeypatch.setattr(
            module,
            "parse_args",
            lambda: make_manage_job_schedules_args(**overrides),
        )
        return module.main()

    return _run


def test_main_requires_at_least_one_time_when_registering(_run_main_with_args, capsys) -> None:
    assert _run_main_with_args() == 2
    assert "Provide at least one schedule time" in capsys.readouterr().err


def test_main_registers_tasks_with_repo_root(monkeypatch, tmp_path: Path, _run_main_with_args) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(module, "get_repo_root", lambda _file: tmp_path)

    def fake_register(tasks, *, repo_root, python_exe, dry_run, **_kwargs):
        captured["tasks"] = tasks
        captured["repo_root"] = repo_root
        captured["python_exe"] = python_exe
        captured["dry_run"] = dry_run
        return 0

    monkeypatch.setattr(module, "register_tasks_for_platform", fake_register)

    assert (
        _run_main_with_args(
            daily_paper_trading_time="13:10",
            daily_snapshot_time="13:40",
            enable_daily_snapshot=True,
        )
        == 0
    )
    tasks = captured["tasks"]
    assert isinstance(tasks, list)
    assert len(tasks) == 2
    assert captured["repo_root"] == tmp_path
    assert captured["python_exe"] == "/tmp/.venv/bin/python"


def test_main_registers_weekly_backup_with_daily_tasks(monkeypatch, tmp_path: Path, _run_main_with_args) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(module, "get_repo_root", lambda _file: tmp_path)

    def fake_register(tasks, *, repo_root, python_exe, dry_run, **_kwargs):
        captured["tasks"] = tasks
        return 0

    monkeypatch.setattr(module, "register_tasks_for_platform", fake_register)

    assert (
        _run_main_with_args(
            daily_paper_trading_time="13:10",
            weekly_db_backup_time="02:00",
            weekly_db_backup_day_of_week="Monday",
        )
        == 0
    )
    tasks = captured["tasks"]
    assert len(tasks) == 2
    weekly = tasks[1]
    assert weekly.task_name == r"Trading\WeeklyDbBackup"
    assert weekly.schedule_kind == "weekly"
    assert weekly.day_of_week == "Monday"


def test_main_unregisters_all_default_task_names(monkeypatch, _run_main_with_args) -> None:
    captured: dict[str, object] = {}

    def fake_unregister(task_names, *, dry_run, **_kwargs):
        captured["task_names"] = task_names
        captured["dry_run"] = dry_run
        return 0

    monkeypatch.setattr(module, "unregister_tasks_for_platform", fake_unregister)

    assert _run_main_with_args(unregister=True) == 0
    assert captured["task_names"] == [
        r"Trading\DailyPaperTrading",
        r"Trading\DailyPaperTradingFallback",
        r"Trading\DailyChallengerShadowEval",
        r"Trading\DailySnapshot",
        r"Trading\DailyTraderHealthCheck",
        r"Trading\WeeklyDbBackup",
    ]


def test_main_forwards_scheduler_options_to_register(monkeypatch, tmp_path: Path, _run_main_with_args) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(module, "get_repo_root", lambda _file: tmp_path)

    def fake_register(tasks, *, repo_root, python_exe, dry_run, scheduler_type, wake_system, env_file):
        captured["scheduler_type"] = scheduler_type
        captured["wake_system"] = wake_system
        captured["env_file"] = env_file
        return 0

    monkeypatch.setattr(module, "register_tasks_for_platform", fake_register)

    assert (
        _run_main_with_args(
            daily_paper_trading_time="13:00",
            scheduler="systemd",
            wake_system=False,
            env_file="/etc/trading/.env",
        )
        == 0
    )
    assert captured["scheduler_type"] == "systemd"
    assert captured["wake_system"] is False
    assert captured["env_file"] == Path("/etc/trading/.env")


def test_main_register_converts_empty_env_file_to_none(monkeypatch, tmp_path: Path, _run_main_with_args) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(module, "get_repo_root", lambda _file: tmp_path)

    def fake_register(tasks, *, env_file, **_kwargs):
        captured["env_file"] = env_file
        return 0

    monkeypatch.setattr(module, "register_tasks_for_platform", fake_register)

    assert _run_main_with_args(daily_paper_trading_time="13:00") == 0
    assert captured["env_file"] is None


def test_main_unregister_forwards_scheduler_and_repo_root(monkeypatch, tmp_path: Path, _run_main_with_args) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(module, "get_repo_root", lambda _file: tmp_path)

    def fake_unregister(task_names, *, dry_run, scheduler_type, repo_root):
        captured["scheduler_type"] = scheduler_type
        captured["repo_root"] = repo_root
        return 0

    monkeypatch.setattr(module, "unregister_tasks_for_platform", fake_unregister)

    assert _run_main_with_args(unregister=True, scheduler="cron") == 0
    assert captured["scheduler_type"] == "cron"
    assert captured["repo_root"] == tmp_path


def test_main_rejects_non_positive_health_check_threshold(_run_main_with_args, capsys) -> None:
    assert _run_main_with_args(health_check_max_age_hours=0) == 2
    assert "--health-check-max-age-hours must be > 0" in capsys.readouterr().err


def test_main_rejects_invalid_shadow_eval_lead_minutes(_run_main_with_args, capsys) -> None:
    assert _run_main_with_args(shadow_eval_lead_minutes=0) == 2
    assert "--shadow-eval-lead-minutes" in capsys.readouterr().err


def test_main_returns_one_when_scheduler_raises(monkeypatch, tmp_path: Path, _run_main_with_args, capsys) -> None:
    monkeypatch.setattr(module, "get_repo_root", lambda _file: tmp_path)
    monkeypatch.setattr(
        module,
        "register_tasks_for_platform",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    assert _run_main_with_args(daily_paper_trading_time="13:10") == 1
    assert "Error: boom" in capsys.readouterr().err


def test_main_returns_nonzero_scheduler_code(monkeypatch, tmp_path: Path, _run_main_with_args, capsys) -> None:
    monkeypatch.setattr(module, "get_repo_root", lambda _file: tmp_path)
    monkeypatch.setattr(module, "register_tasks_for_platform", lambda *args, **kwargs: 7)

    assert _run_main_with_args(daily_paper_trading_time="13:10") == 7
    assert "Scheduler command returned a non-zero exit code." in capsys.readouterr().err


def test_manage_job_schedules_module_main_entrypoint(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["manage_job_schedules"])

    with pytest.raises(SystemExit) as excinfo:
        run_module_as_main(module.__name__)

    assert excinfo.value.code == 2
    assert "Provide at least one schedule time" in capsys.readouterr().err
