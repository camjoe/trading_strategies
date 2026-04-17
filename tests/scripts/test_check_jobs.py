from __future__ import annotations

import datetime as dt
from pathlib import Path

from scripts import check_jobs


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_daily_job_checks_cover_snapshot_and_backtest_refresh(tmp_path: Path, monkeypatch) -> None:
    today_tag = dt.date.today().strftime("%Y%m%d")
    monkeypatch.setattr(check_jobs, "LOGS_DIR", tmp_path)

    _write(
        tmp_path / f"daily_snapshot_{today_tag}_133000.log",
        f"ok\n{check_jobs.DAILY_SNAPSHOT_SENTINEL}\n",
    )
    _write(
        tmp_path / f"daily_backtest_refresh_{today_tag}_134500.log",
        f"ok\n{check_jobs.DAILY_BACKTEST_REFRESH_SENTINEL}\n",
    )

    snapshot = check_jobs._check_daily_snapshot()
    refresh = check_jobs._check_daily_backtest_refresh()

    assert snapshot["today_complete"] is True
    assert snapshot["job"] == "Daily Snapshot"
    assert snapshot["run_cmd"] == [check_jobs.sys.executable, "-m", check_jobs.DAILY_SNAPSHOT_SCRIPT, "--enable-run"]

    assert refresh["today_complete"] is True
    assert refresh["job"] == "Daily Backtest Refresh"
    assert refresh["run_cmd"] == [
        check_jobs.sys.executable,
        "-m",
        check_jobs.DAILY_BACKTEST_REFRESH_SCRIPT,
        "--accounts",
        "all",
        "--enable-run",
    ]


def test_main_run_missing_triggers_new_daily_jobs(monkeypatch, capsys) -> None:
    daily = {
        "job": "Daily Paper Trading",
        "today_complete": True,
        "run_cmd": ["paper"],
        "today_ran": True,
        "today_log": None,
        "last_success": dt.date.today(),
        "last_success_log": None,
    }
    snapshot = {
        "job": "Daily Snapshot",
        "today_complete": False,
        "run_cmd": ["snapshot"],
        "today_ran": False,
        "today_log": None,
        "last_success": None,
        "last_success_log": None,
    }
    refresh = {
        "job": "Daily Backtest Refresh",
        "today_complete": False,
        "run_cmd": ["refresh"],
        "today_ran": False,
        "today_log": None,
        "last_success": None,
        "last_success_log": None,
    }
    weekly = {
        "job": "Weekly DB Backup",
        "week_tag": "2026_W16",
        "this_week_complete": True,
        "run_cmd": ["weekly"],
        "this_week_ran": True,
        "this_week_log": None,
        "last_success": dt.date.today(),
        "last_success_log": None,
    }

    triggered: list[tuple[list[str], str]] = []
    argv = ["check_jobs.py", "--run-missing"]

    monkeypatch.setattr(check_jobs, "_check_daily", lambda: daily)
    monkeypatch.setattr(check_jobs, "_check_daily_snapshot", lambda: snapshot)
    monkeypatch.setattr(check_jobs, "_check_daily_backtest_refresh", lambda: refresh)
    monkeypatch.setattr(check_jobs, "_check_weekly", lambda: weekly)
    monkeypatch.setattr(check_jobs, "_trigger", lambda run_cmd, label: triggered.append((run_cmd, label)))
    monkeypatch.setattr(check_jobs.sys, "argv", argv)

    result = check_jobs.main()

    assert result == 1
    assert triggered == [
        (["snapshot"], "Daily Snapshot"),
        (["refresh"], "Daily Backtest Refresh"),
    ]
    output = capsys.readouterr().out
    assert "Daily Snapshot" in output
    assert "Daily Backtest Refresh" in output
