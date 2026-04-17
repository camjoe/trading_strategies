from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path


def _load():
    return importlib.import_module("trading.interfaces.runtime.jobs.manage_job_schedules")


def _args(**overrides):
    defaults = {
        "daily_paper_trading_time": "",
        "daily_paper_trading_task_name": r"Trading\DailyPaperTrading",
        "daily_paper_trading_fallback_time": "",
        "daily_paper_trading_fallback_task_name": r"Trading\DailyPaperTradingFallback",
        "daily_snapshot_time": "",
        "daily_snapshot_task_name": r"Trading\DailySnapshot",
        "enable_daily_snapshot": False,
        "daily_backtest_refresh_time": "",
        "daily_backtest_refresh_task_name": r"Trading\DailyBacktestRefresh",
        "enable_daily_backtest_refresh": False,
        "health_check_time": "",
        "health_check_task_name": r"Trading\DailyTraderHealthCheck",
        "health_check_max_age_hours": 24.0,
        "weekly_db_backup_time": "",
        "weekly_db_backup_day_of_week": "Sunday",
        "weekly_db_backup_task_name": r"Trading\WeeklyDbBackup",
        "unregister": False,
        "dry_run": False,
        "python": "/tmp/venv/bin/python",
    }
    defaults.update(overrides)
    return types.SimpleNamespace(**defaults)


def test_build_scheduled_tasks_includes_requested_jobs() -> None:
    module = _load()
    tasks = module.build_scheduled_tasks(
        _args(
            daily_paper_trading_time="13:10",
            daily_paper_trading_fallback_time="15:45",
            daily_snapshot_time="13:30",
            enable_daily_snapshot=True,
            daily_backtest_refresh_time="14:10",
            health_check_time="16:00",
            weekly_db_backup_time="02:00",
            weekly_db_backup_day_of_week="Sunday",
        )
    )

    assert [task.task_name for task in tasks] == [
        r"Trading\DailyPaperTrading",
        r"Trading\DailyPaperTradingFallback",
        r"Trading\DailySnapshot",
        r"Trading\DailyBacktestRefresh",
        r"Trading\DailyTraderHealthCheck",
        r"Trading\WeeklyDbBackup",
    ]
    assert tasks[1].args == ("--run-source", "scheduled-daily-fallback")
    assert tasks[2].args == ("--enable-run",)
    assert tasks[3].args == ()
    assert tasks[4].args == ("--max-age-hours", "24.0")
    assert tasks[5].schedule_kind == "weekly"
    assert tasks[5].day_of_week == "Sunday"


def test_build_scheduled_tasks_omits_optional_jobs_without_times() -> None:
    module = _load()
    tasks = module.build_scheduled_tasks(_args(daily_paper_trading_time="13:10"))

    assert len(tasks) == 1
    assert tasks[0].module == module.DAILY_PAPER_TRADING_MODULE


def test_main_requires_at_least_one_time_when_registering(monkeypatch, capsys) -> None:
    module = _load()
    monkeypatch.setattr(module, "parse_args", lambda: _args())

    assert module.main() == 2
    assert "Provide at least one schedule time" in capsys.readouterr().err


def test_main_registers_tasks_with_repo_root(monkeypatch, tmp_path: Path) -> None:
    module = _load()
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        module,
        "parse_args",
        lambda: _args(
            daily_paper_trading_time="13:10",
            daily_snapshot_time="13:40",
            enable_daily_snapshot=True,
        ),
    )
    monkeypatch.setattr(module, "get_repo_root", lambda _file: tmp_path)

    def fake_register(tasks, *, repo_root, python_exe, dry_run):
        captured["tasks"] = tasks
        captured["repo_root"] = repo_root
        captured["python_exe"] = python_exe
        captured["dry_run"] = dry_run
        return 0

    monkeypatch.setattr(module, "register_tasks_for_platform", fake_register)

    assert module.main() == 0
    tasks = captured["tasks"]
    assert isinstance(tasks, list)
    assert len(tasks) == 2
    assert captured["repo_root"] == tmp_path
    assert captured["python_exe"] == "/tmp/venv/bin/python"


def test_main_registers_weekly_backup_with_daily_tasks(monkeypatch, tmp_path: Path) -> None:
    module = _load()
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        module,
        "parse_args",
        lambda: _args(
            daily_paper_trading_time="13:10",
            weekly_db_backup_time="02:00",
            weekly_db_backup_day_of_week="Monday",
        ),
    )
    monkeypatch.setattr(module, "get_repo_root", lambda _file: tmp_path)

    def fake_register(tasks, *, repo_root, python_exe, dry_run):
        captured["tasks"] = tasks
        return 0

    monkeypatch.setattr(module, "register_tasks_for_platform", fake_register)

    assert module.main() == 0
    tasks = captured["tasks"]
    assert len(tasks) == 2
    weekly = tasks[1]
    assert weekly.task_name == r"Trading\WeeklyDbBackup"
    assert weekly.schedule_kind == "weekly"
    assert weekly.day_of_week == "Monday"


def test_main_unregisters_all_default_task_names(monkeypatch) -> None:
    module = _load()
    captured: dict[str, object] = {}

    monkeypatch.setattr(module, "parse_args", lambda: _args(unregister=True))

    def fake_unregister(task_names, *, dry_run):
        captured["task_names"] = task_names
        captured["dry_run"] = dry_run
        return 0

    monkeypatch.setattr(module, "unregister_tasks_for_platform", fake_unregister)

    assert module.main() == 0
    assert captured["task_names"] == [
        r"Trading\DailyPaperTrading",
        r"Trading\DailyPaperTradingFallback",
        r"Trading\DailySnapshot",
        r"Trading\DailyBacktestRefresh",
        r"Trading\DailyTraderHealthCheck",
        r"Trading\WeeklyDbBackup",
    ]


def test_main_rejects_non_positive_health_check_threshold(monkeypatch, capsys) -> None:
    module = _load()
    monkeypatch.setattr(module, "parse_args", lambda: _args(health_check_max_age_hours=0))

    assert module.main() == 2
    assert "--health-check-max-age-hours must be > 0" in capsys.readouterr().err
