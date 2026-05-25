from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import trading.interfaces.runtime.jobs.maintenance.replay_daily_runs as replay_module
from tests.trading.interfaces.runtime.jobs.loaders import (
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
        lambda *_a, **_k: {
            "report_date": "2020-01-15",
            "account_count": 0,
            "account_reports": [],
            "artifact_path": "",
            "notify_on_success": False,
        },
    )


@pytest.fixture(autouse=True)
def _stub_daily_runtime_defaults(monkeypatch):
    set_runtime_eligible_accounts(monkeypatch, DAILY_PAPER_TRADING_MODULE, ["acct1"])
    monkeypatch.setattr(f"{DAILY_PAPER_TRADING_REPORTING_MODULE}.ensure_db", lambda: None)


def _run_replay_main(monkeypatch, root: Path, args: list[str]) -> int:
    monkeypatch.setattr(
        sys,
        "argv",
        ["replay_daily_runs", *args, "--repo-root", str(root)],
    )
    return replay_module.main()


def _run_daily_as_of(monkeypatch, root: Path, args: list[str]) -> int:
    return run_runtime_job_main(
        monkeypatch,
        root,
        DAILY_PAPER_TRADING_MODULE,
        ["--accounts", "acct1", *args],
    )


def test_as_of_date_uses_date_prefix_in_log_name(monkeypatch, job_root: Path) -> None:
    """--as-of-date YYYY-MM-DD should name log/artifact with that date prefix."""
    _run_daily_as_of(monkeypatch, job_root, ["--as-of-date", "2020-01-15", "--force-run"])

    logs_dir = job_root / "local" / "logs"
    log_files = list(logs_dir.glob("daily_paper_trading_20200115_*.log"))
    assert log_files, "Expected a log file prefixed with 20200115"


def test_as_of_date_dedup_guard_uses_override_date(monkeypatch, job_root: Path, capsys) -> None:
    """--as-of-date dedup guard should key off the override date, not today."""
    write_completed_runtime_log(
        job_root,
        filename_prefix="daily_paper_trading",
        tag="20200115",
        sentinel=daily_module.COMPLETE_SENTINEL,
        timestamp="000000",
    )

    code = _run_daily_as_of(monkeypatch, job_root, ["--as-of-date", "2020-01-15"])

    assert code == 0
    out = capsys.readouterr().out
    assert "already completed for 2020-01-15" in out


def test_as_of_date_invalid_value_returns_1(monkeypatch, job_root: Path, capsys) -> None:
    code = _run_daily_as_of(monkeypatch, job_root, ["--as-of-date", "not-a-date"])
    assert code == 1


def test_as_of_date_recorded_in_artifact(monkeypatch, job_root: Path) -> None:
    """as_of_date field should appear in the artifact JSON."""
    _run_daily_as_of(monkeypatch, job_root, ["--as-of-date", "2020-01-15", "--force-run"])

    export_dir = job_root / "local" / "exports" / "daily_paper_trading"
    payload = load_single_artifact_json(
        export_dir,
        "daily_paper_trading_20200115_*.json",
    )
    assert payload.get("as_of_date") == "2020-01-15"


# ---------------------------------------------------------------------------
# replay_daily_runs tests
# ---------------------------------------------------------------------------


def test_replay_dry_run_lists_missing_dates(monkeypatch, job_root: Path, capsys) -> None:
    """--dry-run should print missing dates and return 0 without executing any runs."""
    result = _run_replay_main(
        monkeypatch,
        job_root,
        ["--from-date", "2026-05-01", "--to-date", "2026-05-03", "--dry-run"],
    )
    out = capsys.readouterr().out
    assert result == 0
    assert "DRY RUN" in out
    assert "2026-05-01" in out


def test_replay_nothing_to_do_when_all_complete(monkeypatch, job_root: Path, capsys) -> None:
    """If every date already has a sentinel, replay should report nothing to do."""
    for day in ("20260501", "20260502", "20260503"):
        write_completed_runtime_log(
            job_root,
            filename_prefix="daily_paper_trading",
            tag=day,
            sentinel=daily_module.COMPLETE_SENTINEL,
            timestamp="000000",
        )

    result = _run_replay_main(
        monkeypatch,
        job_root,
        ["--from-date", "2026-05-01", "--to-date", "2026-05-03", "--dry-run"],
    )
    out = capsys.readouterr().out
    assert result == 0
    assert "Nothing to replay" in out


def test_replay_executes_missing_dates(monkeypatch, job_root: Path) -> None:
    """Replay should call subprocess.run for each missing date."""
    # Only 2026-05-02 is pre-completed
    write_completed_runtime_log(
        job_root,
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
        job_root,
        ["--from-date", "2026-05-01", "--to-date", "2026-05-03"],
    )
    assert result == 0
    replayed_dates = [cmd[cmd.index("--as-of-date") + 1] for cmd in called if "--as-of-date" in cmd]
    assert "2026-05-01" in replayed_dates
    assert "2026-05-03" in replayed_dates
    assert "2026-05-02" not in replayed_dates  # already complete


def test_replay_reports_failure_when_subprocess_fails(monkeypatch, job_root: Path) -> None:
    """Replay should return 1 if any date's subprocess exits non-zero."""
    monkeypatch.setattr(
        replay_module.subprocess,
        "run",
        lambda cmd, *, check: SimpleNamespace(returncode=1),
    )
    result = _run_replay_main(
        monkeypatch,
        job_root,
        ["--from-date", "2026-05-01", "--to-date", "2026-05-01"],
    )
    assert result == 1


def test_replay_from_date_after_to_date_returns_1(monkeypatch, job_root: Path) -> None:
    result = _run_replay_main(
        monkeypatch,
        job_root,
        ["--from-date", "2026-05-05", "--to-date", "2026-05-01"],
    )
    assert result == 1
