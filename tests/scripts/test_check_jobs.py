from __future__ import annotations

import datetime as dt
from pathlib import Path

from scripts import check_jobs


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_main_run_missing_triggers_incomplete_daily_job(monkeypatch, capsys) -> None:
    daily = {
        "job": "Daily Paper Trading",
        "today_complete": False,
        "run_cmd": ["paper"],
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
    monkeypatch.setattr(check_jobs, "_check_weekly", lambda: weekly)
    monkeypatch.setattr(check_jobs, "_trigger", lambda run_cmd, label: triggered.append((run_cmd, label)))
    monkeypatch.setattr(check_jobs.sys, "argv", argv)

    result = check_jobs.main()

    assert result == 1
    assert triggered == [
        (["paper"], "Daily Paper Trading"),
    ]
    output = capsys.readouterr().out
    assert "Daily Paper Trading" in output
