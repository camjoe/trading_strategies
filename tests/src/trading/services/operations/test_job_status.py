from __future__ import annotations

import datetime as dt
from pathlib import Path

from trading.interfaces.runtime.jobs.job_helpers import day_tag, month_tag, week_tag
from trading.services.operations import job_status


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


NOW = dt.datetime(2026, 9, 12, 14, 30, 0)


def test_evaluate_all_jobs_covers_every_monitored_job(tmp_path: Path) -> None:
    statuses = job_status.evaluate_all_jobs(logs_dir=tmp_path, now=NOW)
    assert [s.job.key for s in statuses] == [job.key for job in job_status.MONITORED_JOBS]
    # The challenger shadow-eval and the governance jobs are all present, not just
    # the daily run and the weekly backup.
    keys = {s.job.key for s in statuses}
    assert "daily_challenger_shadow_eval" in keys
    assert "weekly_governance_w1_leaderboard" in keys
    assert "monthly_governance_m3_performance_audit" in keys


def test_run_hint_is_a_runnable_module_command() -> None:
    for job in job_status.MONITORED_JOBS:
        assert job.run_hint.startswith("python -m ")


def test_status_ok_when_current_period_log_has_sentinel(tmp_path: Path) -> None:
    day = day_tag(NOW)
    _write(
        tmp_path / f"daily_paper_trading_{day}_143001.log",
        f"start\n{job_status.DAILY_PAPER_TRADING_COMPLETE_SENTINEL}\n",
    )
    result = job_status.evaluate_job(job_status.MONITORED_JOBS[0], logs_dir=tmp_path, now=NOW)
    assert result.status == "ok"
    assert result.current_run_complete is True
    assert result.current_log is not None
    assert result.last_success_log is not None


def test_status_warning_when_current_log_lacks_sentinel(tmp_path: Path) -> None:
    day = day_tag(NOW)
    _write(tmp_path / f"daily_paper_trading_{day}_143001.log", "started but never finished\n")
    result = job_status.evaluate_job(job_status.MONITORED_JOBS[0], logs_dir=tmp_path, now=NOW)
    assert result.status == "warning"
    assert result.current_run_present is True
    assert result.current_run_complete is False


def test_status_missing_and_last_success_reads_an_older_log(tmp_path: Path) -> None:
    older_day = day_tag(NOW - dt.timedelta(days=3))
    _write(
        tmp_path / f"daily_paper_trading_{older_day}_100000.log",
        f"{job_status.DAILY_PAPER_TRADING_COMPLETE_SENTINEL}\n",
    )
    result = job_status.evaluate_job(job_status.MONITORED_JOBS[0], logs_dir=tmp_path, now=NOW)
    assert result.status == "missing"
    assert result.current_run_present is False
    # A completed run from an earlier day is still reported as the last success.
    assert result.last_success_log is not None


def test_daily_paper_trading_pattern_excludes_the_startup_log(tmp_path: Path) -> None:
    day = day_tag(NOW)
    # Only a startup log exists; it must not count as a run.
    _write(tmp_path / f"daily_paper_trading_startup_{day}.log", "boot\n")
    result = job_status.evaluate_job(job_status.MONITORED_JOBS[0], logs_dir=tmp_path, now=NOW)
    assert result.status == "missing"


def test_period_tag_matches_job_helpers_spellings() -> None:
    # The tags here find the files job_helpers named; they must not drift apart.
    assert job_status.period_tag("daily", NOW) == day_tag(NOW)
    assert job_status.period_tag("weekly", NOW) == week_tag(NOW)
    assert job_status.period_tag("monthly", NOW) == month_tag(NOW)


def test_fetch_schedule_status_returns_none_when_missing(tmp_path: Path) -> None:
    from trading.services.operations.schedule_status import fetch_schedule_status

    assert fetch_schedule_status(tmp_path / "absent.json") is None


def test_fetch_schedule_status_reads_written_artifact(tmp_path: Path) -> None:
    from trading.services.operations.schedule_status import fetch_schedule_status

    artifact = tmp_path / "schedule_status.json"
    artifact.write_text('{"in_sync": true, "jobs": []}', encoding="utf-8")
    result = fetch_schedule_status(artifact)
    assert result == {"in_sync": True, "jobs": []}


def test_fetch_schedule_status_returns_none_on_bad_json(tmp_path: Path) -> None:
    from trading.services.operations.schedule_status import fetch_schedule_status

    artifact = tmp_path / "schedule_status.json"
    artifact.write_text("{not json", encoding="utf-8")
    assert fetch_schedule_status(artifact) is None
