from __future__ import annotations

from tests.support.runtime_jobs import make_manage_job_schedules_args, manage_job_schedules as module


def test_build_scheduled_tasks_includes_requested_jobs() -> None:
    tasks = module.build_scheduled_tasks(
        make_manage_job_schedules_args(
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
    tasks = module.build_scheduled_tasks(
        make_manage_job_schedules_args(daily_paper_trading_time="13:10")
    )

    assert len(tasks) == 1
    assert tasks[0].module == module.DAILY_PAPER_TRADING_MODULE
