from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import trading.interfaces.runtime.jobs.maintenance.replay_daily_runs as replay_module
from tests.support.runtime_jobs import (
    DAILY_PAPER_TRADING_MODULE,
    DAILY_PAPER_TRADING_REPORTING_MODULE,
    daily_paper_trading as daily_module,
    load_single_artifact_json,
    run_runtime_job_main,
    set_runtime_eligible_accounts,
    write_completed_runtime_log,
)


# ---------------------------------------------------------------------------
# --as-of-date flag tests (on daily_paper_trading itself)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _stub_operator_report(monkeypatch):
    monkeypatch.setattr(
        f"{DAILY_PAPER_TRADING_MODULE}._build_daily_operator_report",
        lambda *_a, **_k: {"report_date": "2020-01-15", "account_count": 0, "account_reports": [], "artifact_path": "", "notify_on_success": False},
    )


@pytest.fixture(autouse=True)
def _stub_daily_runtime_defaults(monkeypatch):
    set_runtime_eligible_accounts(monkeypatch, DAILY_PAPER_TRADING_MODULE, ["acct1"])
    monkeypatch.setattr(f"{DAILY_PAPER_TRADING_REPORTING_MODULE}.ensure_db", lambda: None)


def _run_replay_main(monkeypatch, tmp_path: Path, args: list[str]) -> int:
    monkeypatch.setattr(
        sys,
        "argv",
        ["replay_daily_runs", *args, "--repo-root", str(tmp_path)],
    )
    return replay_module.main()


def _run_daily_as_of(monkeypatch, tmp_path: Path, args: list[str]) -> int:
    return run_runtime_job_main(
        monkeypatch,
        tmp_path,
        DAILY_PAPER_TRADING_MODULE,
        ["--accounts", "acct1", *args],
    )


def test_as_of_date_uses_date_prefix_in_log_name(monkeypatch, tmp_path: Path) -> None:
    """--as-of-date YYYY-MM-DD should name log/artifact with that date prefix."""
    _run_daily_as_of(monkeypatch, tmp_path, ["--as-of-date", "2020-01-15", "--force-run"])

    logs_dir = tmp_path / "local" / "logs"
    log_files = list(logs_dir.glob("daily_paper_trading_20200115_*.log"))
    assert log_files, "Expected a log file prefixed with 20200115"


def test_as_of_date_dedup_guard_uses_override_date(monkeypatch, tmp_path: Path, capsys) -> None:
    """--as-of-date dedup guard should key off the override date, not today."""
    log_dir = tmp_path / "local" / "logs"
    log_dir.mkdir(parents=True)
    # Pre-write a sentinel for the override date
    write_completed_runtime_log(
        tmp_path,
        filename_prefix="daily_paper_trading",
        tag="20200115",
        sentinel=daily_module.COMPLETE_SENTINEL,
        timestamp="000000",
    )

    code = _run_daily_as_of(monkeypatch, tmp_path, ["--as-of-date", "2020-01-15"])

    assert code == 0
    out = capsys.readouterr().out
    assert "already completed for 2020-01-15" in out


def test_as_of_date_invalid_value_returns_1(monkeypatch, tmp_path: Path, capsys) -> None:
    code = _run_daily_as_of(monkeypatch, tmp_path, ["--as-of-date", "not-a-date"])
    assert code == 1


def test_as_of_date_recorded_in_artifact(monkeypatch, tmp_path: Path) -> None:
    """as_of_date field should appear in the artifact JSON."""
    _run_daily_as_of(monkeypatch, tmp_path, ["--as-of-date", "2020-01-15", "--force-run"])

    export_dir = tmp_path / "local" / "exports" / "daily_paper_trading"
    payload = load_single_artifact_json(
        export_dir,
        "daily_paper_trading_20200115_*.json",
    )
    assert payload.get("as_of_date") == "2020-01-15"


# ---------------------------------------------------------------------------
# replay_daily_runs tests
# ---------------------------------------------------------------------------


def test_replay_dry_run_lists_missing_dates(monkeypatch, tmp_path: Path, capsys) -> None:
    """--dry-run should print missing dates and return 0 without executing any runs."""
    logs_dir = tmp_path / "local" / "logs"
    logs_dir.mkdir(parents=True)

    result = _run_replay_main(
        monkeypatch,
        tmp_path,
        ["--from-date", "2026-05-01", "--to-date", "2026-05-03", "--dry-run"],
    )
    out = capsys.readouterr().out
    assert result == 0
    assert "DRY RUN" in out
    assert "2026-05-01" in out


def test_replay_nothing_to_do_when_all_complete(monkeypatch, tmp_path: Path, capsys) -> None:
    """If every date already has a sentinel, replay should report nothing to do."""
    logs_dir = tmp_path / "local" / "logs"
    logs_dir.mkdir(parents=True)
    for day in ("20260501", "20260502", "20260503"):
        write_completed_runtime_log(
            tmp_path,
            filename_prefix="daily_paper_trading",
            tag=day,
            sentinel=daily_module.COMPLETE_SENTINEL,
            timestamp="000000",
        )

    result = _run_replay_main(
        monkeypatch,
        tmp_path,
        ["--from-date", "2026-05-01", "--to-date", "2026-05-03", "--dry-run"],
    )
    out = capsys.readouterr().out
    assert result == 0
    assert "Nothing to replay" in out


def test_replay_executes_missing_dates(monkeypatch, tmp_path: Path) -> None:
    """Replay should call subprocess.run for each missing date."""
    logs_dir = tmp_path / "local" / "logs"
    logs_dir.mkdir(parents=True)
    # Only 2026-05-02 is pre-completed
    write_completed_runtime_log(
        tmp_path,
        filename_prefix="daily_paper_trading",
        tag="20260502",
        sentinel=daily_module.COMPLETE_SENTINEL,
        timestamp="000000",
    )

    called: list[list[str]] = []

    def _fake_run(cmd, *, check):
        called.append(cmd)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(replay_module.subprocess, "run", _fake_run)
    result = _run_replay_main(
        monkeypatch,
        tmp_path,
        ["--from-date", "2026-05-01", "--to-date", "2026-05-03"],
    )
    assert result == 0
    replayed_dates = [
        cmd[cmd.index("--as-of-date") + 1]
        for cmd in called
        if "--as-of-date" in cmd
    ]
    assert "2026-05-01" in replayed_dates
    assert "2026-05-03" in replayed_dates
    assert "2026-05-02" not in replayed_dates  # already complete


def test_replay_reports_failure_when_subprocess_fails(monkeypatch, tmp_path: Path) -> None:
    """Replay should return 1 if any date's subprocess exits non-zero."""
    logs_dir = tmp_path / "local" / "logs"
    logs_dir.mkdir(parents=True)

    monkeypatch.setattr(
        replay_module.subprocess, "run",
        lambda cmd, *, check: SimpleNamespace(returncode=1),
    )
    result = _run_replay_main(
        monkeypatch,
        tmp_path,
        ["--from-date", "2026-05-01", "--to-date", "2026-05-01"],
    )
    assert result == 1


def test_replay_from_date_after_to_date_returns_1(monkeypatch, tmp_path: Path) -> None:
    result = _run_replay_main(
        monkeypatch,
        tmp_path,
        ["--from-date", "2026-05-05", "--to-date", "2026-05-01"],
    )
    assert result == 1
