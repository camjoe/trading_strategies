from __future__ import annotations

import sys

import pytest

from tests.src.trading.interfaces.runtime.jobs.loaders import (
    make_manage_job_schedules_args,
    manage_job_schedules as module,
)


def test_parse_args_reads_cli_flags(monkeypatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "manage_job_schedules",
            "--daily-paper-trading-time",
            "13:10",
            "--daily-backtest-refresh-time",
            "14:10",
            "--enable-daily-backtest-refresh",
            "--weekly-db-backup-time",
            "02:00",
            "--weekly-db-backup-day-of-week",
            "Monday",
            "--python",
            "./.venv/bin/python",
        ],
    )

    args = module.parse_args()

    assert args.daily_paper_trading_time == "13:10"
    assert args.daily_backtest_refresh_time == "14:10"
    assert args.enable_daily_backtest_refresh is True
    assert args.weekly_db_backup_time == "02:00"
    assert args.weekly_db_backup_day_of_week == "Monday"
    assert args.python == "./.venv/bin/python"


def test_parse_args_reads_scheduler_options(monkeypatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "manage_job_schedules",
            "--daily-paper-trading-time",
            "13:00",
            "--scheduler",
            "systemd",
            "--no-wake-system",
            "--env-file",
            "/etc/trading/.env",
        ],
    )

    args = module.parse_args()

    assert args.scheduler == "systemd"
    assert args.wake_system is False
    assert args.env_file == "/etc/trading/.env"


def test_parse_args_scheduler_option_defaults(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["manage_job_schedules", "--daily-paper-trading-time", "13:00"])

    args = module.parse_args()

    assert args.scheduler == "auto"
    assert args.wake_system is True
    assert args.env_file == ""


def test_default_python_prefers_venv_interpreter(monkeypatch, tmp_path) -> None:
    venv_python = tmp_path / "bin" / "python"
    venv_python.parent.mkdir(parents=True)
    venv_python.write_text("")
    monkeypatch.setattr(module.sys, "prefix", str(tmp_path))
    monkeypatch.setattr(module.sys, "base_prefix", str(tmp_path / "base"))

    assert module._default_python() == str(venv_python)


def test_default_python_falls_back_to_sys_executable_outside_venv(monkeypatch) -> None:
    monkeypatch.setattr(module.sys, "prefix", "/same")
    monkeypatch.setattr(module.sys, "base_prefix", "/same")
    monkeypatch.setattr(module.sys, "executable", "/usr/bin/python3")

    assert module._default_python() == "/usr/bin/python3"


def test_derive_shadow_eval_time_wraps_to_previous_day() -> None:
    assert module._derive_shadow_eval_time_from_daily_paper("00:10", lead_minutes=20) == "23:50"


@pytest.mark.parametrize("lead_minutes", [0, module.MINUTES_PER_DAY])
def test_derive_shadow_eval_time_rejects_invalid_lead_minutes(lead_minutes: int) -> None:
    with pytest.raises(ValueError, match="shadow-eval-lead-minutes"):
        module._derive_shadow_eval_time_from_daily_paper("13:10", lead_minutes=lead_minutes)


def test_build_scheduled_tasks_includes_requested_jobs() -> None:
    tasks = module.build_scheduled_tasks(
        make_manage_job_schedules_args(
            daily_paper_trading_time="13:10",
            daily_paper_trading_fallback_time="15:45",
            daily_challenger_shadow_eval_time="12:50",
            enable_daily_challenger_shadow_eval=True,
            daily_snapshot_time="13:30",
            enable_daily_snapshot=True,
            daily_backtest_refresh_time="14:10",
            enable_daily_backtest_refresh=True,
            health_check_time="16:00",
            weekly_db_backup_time="02:00",
            weekly_db_backup_day_of_week="Sunday",
        )
    )

    assert [task.task_name for task in tasks] == [
        r"Trading\DailyPaperTrading",
        r"Trading\DailyPaperTradingFallback",
        r"Trading\DailyChallengerShadowEval",
        r"Trading\DailySnapshot",
        r"Trading\DailyBacktestRefresh",
        r"Trading\DailyTraderHealthCheck",
        r"Trading\WeeklyDbBackup",
    ]
    assert tasks[1].args == ("--run-source", "scheduled-daily-fallback")
    assert tasks[2].args == ("--enable-run",)
    assert tasks[3].args == ("--enable-run",)
    assert tasks[4].args == ("--enable-run",)
    assert tasks[5].args == ("--max-age-hours", "24.0")
    assert tasks[6].schedule_kind == "weekly"
    assert tasks[6].day_of_week == "Sunday"


def test_build_scheduled_tasks_omits_optional_jobs_without_times() -> None:
    tasks = module.build_scheduled_tasks(make_manage_job_schedules_args(daily_paper_trading_time="13:10"))

    assert len(tasks) == 1
    assert tasks[0].module == module.DAILY_PAPER_TRADING_MODULE


def test_build_scheduled_tasks_auto_derives_shadow_eval_time() -> None:
    tasks = module.build_scheduled_tasks(
        make_manage_job_schedules_args(
            daily_paper_trading_time="13:10",
            auto_shadow_eval_from_daily_paper=True,
            shadow_eval_lead_minutes=20,
        )
    )

    assert len(tasks) == 2
    assert tasks[0].module == module.DAILY_PAPER_TRADING_MODULE
    assert tasks[1].module == module.DAILY_CHALLENGER_SHADOW_EVAL_MODULE
    assert tasks[1].time == "12:50"
    assert tasks[1].args == ("--enable-run",)
