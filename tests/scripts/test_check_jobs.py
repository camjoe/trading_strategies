from __future__ import annotations

from pathlib import Path

from scripts import check_jobs
from trading.services.operations.job_status import JobStatus, MonitoredJob


def _status(
    key: str,
    *,
    cadence: str,
    status: str,
    module: str = "pkg.mod",
) -> JobStatus:
    job = MonitoredJob(
        key=key,
        label=key.replace("_", " ").title(),
        cadence=cadence,  # type: ignore[arg-type]
        log_pattern=f"{key}_*.log",
        sentinel="COMPLETE",
        module=module,
    )
    return JobStatus(
        job=job,
        window_label="2026_W37",
        status=status,  # type: ignore[arg-type]
        current_run_present=status != "missing",
        current_run_complete=status == "ok",
        current_log=None,
        last_success_log=None,
    )


def test_is_unhealthy_flags_daily_missing_and_any_warning() -> None:
    assert check_jobs.is_unhealthy(_status("daily_paper_trading", cadence="daily", status="missing")) is True
    assert (
        check_jobs.is_unhealthy(_status("weekly_governance_w1_leaderboard", cadence="weekly", status="warning"))
        is True
    )
    # A monthly job that has not run yet this month is expected, not a failure.
    assert (
        check_jobs.is_unhealthy(_status("monthly_governance_m1_risk_rebaseline", cadence="monthly", status="missing"))
        is False
    )
    assert check_jobs.is_unhealthy(_status("daily_paper_trading", cadence="daily", status="ok")) is False


def test_main_run_missing_triggers_unhealthy_jobs(monkeypatch, capsys) -> None:
    statuses = [
        _status("daily_paper_trading", cadence="daily", status="missing"),
        _status("weekly_db_backup", cadence="weekly", status="ok"),
        _status("monthly_governance_m1_risk_rebaseline", cadence="monthly", status="missing"),
    ]
    triggered: list[str] = []
    monkeypatch.setattr(check_jobs, "evaluate_all_jobs", lambda **_kwargs: statuses)
    monkeypatch.setattr(check_jobs, "_trigger", lambda status: triggered.append(status.job.key))
    monkeypatch.setattr(check_jobs.sys, "argv", ["check_jobs.py", "--run-missing"])

    result = check_jobs.main()

    assert result == 1  # the fake daily run stays missing after the trigger
    # Only the daily run is triggered — the not-yet-run monthly job is not.
    assert triggered == ["daily_paper_trading"]
    assert "Daily Paper Trading" in capsys.readouterr().out


def test_main_healthy_when_only_future_period_jobs_missing(monkeypatch, capsys) -> None:
    statuses = [
        _status("daily_paper_trading", cadence="daily", status="ok"),
        _status("monthly_governance_m3_performance_audit", cadence="monthly", status="missing"),
    ]
    monkeypatch.setattr(check_jobs, "evaluate_all_jobs", lambda **_kwargs: statuses)
    monkeypatch.setattr(check_jobs.sys, "argv", ["check_jobs.py"])

    assert check_jobs.main() == 0
    assert "Tip:" not in capsys.readouterr().out


def test_check_jobs_logs_dir_is_under_local(tmp_path: Path) -> None:
    # Guard the wiring: the report reads the repo's local/logs directory.
    assert check_jobs.LOGS_DIR.name == "logs"
    assert check_jobs.LOGS_DIR.parent.name == "local"
