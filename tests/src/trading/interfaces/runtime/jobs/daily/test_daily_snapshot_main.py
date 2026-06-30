from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest

import trading.interfaces.runtime.jobs.job_runner as job_runner
from trading.interfaces.runtime.jobs.job_helpers import day_tag
from tests.src.trading.interfaces.helpers import run_module_as_main
from tests.src.trading.interfaces.runtime.jobs.loaders import (
    DAILY_SNAPSHOT_MODULE as MODULE_NAME,
    daily_snapshot as module,
    load_single_artifact_json,
    run_runtime_job_with_args,
    write_completed_runtime_log,
)

ENABLE_ARGS = ("--enable-run",)
ENABLE_FORCE_ARGS = ("--enable-run", "--force-run")
EXPORTS_DIR_PARTS = ("local", "exports", "daily_snapshots")
ARTIFACT_GLOB = "daily_snapshot_*.json"


def _run(monkeypatch, tmp_path: Path, args: tuple[str, ...]) -> int:
    return run_runtime_job_with_args(monkeypatch, tmp_path, MODULE_NAME, args)


def _stub_accounts(monkeypatch, accounts: list[str]) -> None:
    monkeypatch.setattr(job_runner, "load_runtime_eligible_account_names", lambda: list(accounts))


def _success(account: str) -> dict[str, object]:
    return {"account": account, "status": "success", "attempts": 1, "last_exit_code": 0}


def _failed(account: str) -> dict[str, object]:
    return {"account": account, "status": "failed", "attempts": 2, "last_exit_code": 1, "transient": True}


class TestValidation:
    def test_rejects_non_positive_max_attempts(self, monkeypatch, tmp_path: Path, capsys) -> None:
        assert _run(monkeypatch, tmp_path, ("--enable-run", "--max-attempts", "0")) == 1
        assert "--max-attempts must be >= 1" in capsys.readouterr().err

    def test_rejects_negative_backoff(self, monkeypatch, tmp_path: Path, capsys) -> None:
        assert _run(monkeypatch, tmp_path, ("--enable-run", "--backoff-seconds", "-0.5")) == 1
        assert "--backoff-seconds must be >= 0" in capsys.readouterr().err


class TestEnableGate:
    def test_reports_disabled_runs(self, monkeypatch, tmp_path: Path, capsys) -> None:
        monkeypatch.delenv(module.DAILY_SNAPSHOT_ENABLED_ENV, raising=False)
        assert _run(monkeypatch, tmp_path, ()) == 0
        assert "Daily snapshot run is disabled" in capsys.readouterr().err

    def test_enabled_via_env(self, monkeypatch, tmp_path: Path) -> None:
        monkeypatch.setenv(module.DAILY_SNAPSHOT_ENABLED_ENV, "true")
        _stub_accounts(monkeypatch, ["acct1"])
        monkeypatch.setattr(module, "run_snapshot_with_retry", lambda **_kwargs: _success("acct1"))

        assert _run(monkeypatch, tmp_path, ("--force-run",)) == 0


class TestAccountResolution:
    def test_reports_account_resolution_errors(self, monkeypatch, tmp_path: Path, capsys) -> None:
        _stub_accounts(monkeypatch, ["acct1"])
        monkeypatch.setattr(
            job_runner, "resolve_accounts", lambda *_a: (_ for _ in ()).throw(ValueError("bad accounts"))
        )
        assert _run(monkeypatch, tmp_path, ENABLE_ARGS) == 1
        assert "bad accounts" in capsys.readouterr().err

    def test_requires_at_least_one_account(self, monkeypatch, tmp_path: Path, capsys) -> None:
        _stub_accounts(monkeypatch, ["acct1"])
        monkeypatch.setattr(job_runner, "resolve_accounts", lambda *_a: [])
        assert _run(monkeypatch, tmp_path, ENABLE_ARGS) == 1
        assert "No accounts specified." in capsys.readouterr().err


class TestDedupGuard:
    def test_writes_skipped_artifact_for_duplicate_run(self, monkeypatch, tmp_path: Path) -> None:
        _stub_accounts(monkeypatch, ["acct1"])
        write_completed_runtime_log(
            tmp_path,
            filename_prefix="daily_snapshot",
            tag=day_tag(dt.datetime.now()),
            sentinel=module.COMPLETE_SENTINEL,
        )

        assert _run(monkeypatch, tmp_path, ENABLE_ARGS) == 0

        payload = load_single_artifact_json(tmp_path.joinpath(*EXPORTS_DIR_PARTS), ARTIFACT_GLOB)
        assert payload["status"] == "skipped"
        assert payload["results"] == []


class TestAccountLoop:
    def test_stops_after_first_failed_account(self, monkeypatch, tmp_path: Path) -> None:
        calls: list[str] = []
        _stub_accounts(monkeypatch, ["acct1", "acct2"])

        def fake_run(**kwargs):
            calls.append(kwargs["account"])
            return _failed(kwargs["account"])

        monkeypatch.setattr(module, "run_snapshot_with_retry", fake_run)

        assert _run(monkeypatch, tmp_path, ENABLE_FORCE_ARGS) == 1
        assert calls == ["acct1"]

        payload = load_single_artifact_json(tmp_path.joinpath(*EXPORTS_DIR_PARTS), ARTIFACT_GLOB)
        assert payload["status"] == "failed"
        assert len(payload["results"]) == 1

        log_text = "\n".join(p.read_text(encoding="utf-8") for p in (tmp_path / "local" / "logs").glob("*.log"))
        assert "Snapshot failed for account=acct1" in log_text

    def test_success_writes_artifact_with_relative_paths(self, monkeypatch, tmp_path: Path) -> None:
        _stub_accounts(monkeypatch, ["acct1"])
        monkeypatch.setattr(module, "run_snapshot_with_retry", lambda **_kwargs: _success("acct1"))

        assert _run(monkeypatch, tmp_path, ENABLE_FORCE_ARGS) == 0

        payload = load_single_artifact_json(tmp_path.joinpath(*EXPORTS_DIR_PARTS), ARTIFACT_GLOB)
        assert payload["status"] == "success"
        assert payload["results"][0]["status"] == "success"
        assert Path(payload["log_path"]).parts[0] == "local"
        assert Path(payload["artifact_path"]).parts[:3] == EXPORTS_DIR_PARTS


def test_daily_snapshot_module_main_entrypoint(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv(module.DAILY_SNAPSHOT_ENABLED_ENV, raising=False)
    monkeypatch.setattr(sys, "argv", ["snapshot", "--repo-root", str(tmp_path)])

    with pytest.raises(SystemExit) as excinfo:
        run_module_as_main(module.__name__)

    assert excinfo.value.code == 0
