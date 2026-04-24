from __future__ import annotations

from pathlib import Path

from tests.support import make_manage_job_schedules_args, manage_job_schedules as module


def test_main_requires_at_least_one_time_when_registering(monkeypatch, capsys) -> None:
    monkeypatch.setattr(module, "parse_args", lambda: make_manage_job_schedules_args())

    assert module.main() == 2
    assert "Provide at least one schedule time" in capsys.readouterr().err


def test_main_registers_tasks_with_repo_root(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        module,
        "parse_args",
        lambda: make_manage_job_schedules_args(
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
    assert captured["python_exe"] == "/tmp/.venv/bin/python"


def test_main_registers_weekly_backup_with_daily_tasks(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        module,
        "parse_args",
        lambda: make_manage_job_schedules_args(
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
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        module,
        "parse_args",
        lambda: make_manage_job_schedules_args(unregister=True),
    )

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
    monkeypatch.setattr(
        module,
        "parse_args",
        lambda: make_manage_job_schedules_args(health_check_max_age_hours=0),
    )

    assert module.main() == 2
    assert "--health-check-max-age-hours must be > 0" in capsys.readouterr().err
