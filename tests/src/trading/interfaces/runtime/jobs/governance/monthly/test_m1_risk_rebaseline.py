from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest

import trading.interfaces.runtime.jobs.governance.monthly.m1_risk_rebaseline as module
from tests.src.trading.interfaces.helpers import run_module_as_main
from tests.src.trading.interfaces.runtime.jobs.loaders import (
    RUN_ALL_ACCOUNTS_ARGS,
    load_single_artifact_json,
    run_runtime_job_with_args,
    stub_runtime_job_basics,
    write_completed_runtime_log,
)
from trading.interfaces.runtime.jobs.job_helpers import month_tag

MODULE_NAME = "trading.interfaces.runtime.jobs.governance.monthly.m1_risk_rebaseline"
RUN_ALL_ARGS = RUN_ALL_ACCOUNTS_ARGS
RUN_ALL_FORCE_ARGS = (*RUN_ALL_ARGS, "--force-run")


def _run_job(monkeypatch, tmp_path: Path, args: tuple[str, ...] = RUN_ALL_ARGS) -> int:
    return run_runtime_job_with_args(monkeypatch, tmp_path, MODULE_NAME, args)


class TestDedupGuard:
    def test_skips_when_already_completed_this_month(self, monkeypatch, tmp_path: Path) -> None:
        now = dt.datetime.now()
        tag = month_tag(now)
        write_completed_runtime_log(
            tmp_path,
            filename_prefix="monthly_governance_m1_risk_rebaseline",
            tag=tag,
            sentinel=module.COMPLETE_SENTINEL,
        )

        result = _run_job(monkeypatch, tmp_path)
        assert result == 0


class TestArtifactStructure:
    def test_writes_artifact_with_correct_top_level_keys(self, monkeypatch, tmp_path: Path) -> None:
        stub_runtime_job_basics(monkeypatch, module)
        monkeypatch.setattr(
            module,
            "fetch_latest_risk_snapshot",
            lambda conn, *, account_id: None,
        )

        result = _run_job(monkeypatch, tmp_path, RUN_ALL_FORCE_ARGS)
        assert result == 0

        payload = load_single_artifact_json(
            tmp_path / "local" / "artifacts",
            "monthly_governance_m1_risk_rebaseline_*.json",
        )
        assert "month" in payload
        assert "generated_at" in payload
        assert "accounts" in payload
        assert isinstance(payload["accounts"], list)

    def test_no_snapshot_produces_null_entry(self, monkeypatch, tmp_path: Path) -> None:
        stub_runtime_job_basics(monkeypatch, module)
        monkeypatch.setattr(
            module,
            "fetch_latest_risk_snapshot",
            lambda conn, *, account_id: None,
        )

        _run_job(monkeypatch, tmp_path, RUN_ALL_FORCE_ARGS)
        payload = load_single_artifact_json(
            tmp_path / "local" / "artifacts",
            "monthly_governance_m1_risk_rebaseline_*.json",
        )
        acct = payload["accounts"][0]
        assert acct["account_name"] == "acct1"
        assert acct["snapshot_time"] is None
        assert "note" in acct

    def test_snapshot_fields_present_when_snapshot_exists(self, monkeypatch, tmp_path: Path) -> None:
        from types import SimpleNamespace

        snapshot = SimpleNamespace(
            snapshot_time="2026-06-01T10:00:00",
            gross_exposure=50000.0,
            net_exposure=30000.0,
            drawdown_pct=-3.5,
            daily_loss_pct=-1.2,
            kill_switch_triggered=False,
            max_symbol_concentration_pct=15.0,
            max_sector_concentration_pct=30.0,
        )
        stub_runtime_job_basics(monkeypatch, module)
        monkeypatch.setattr(
            module,
            "fetch_latest_risk_snapshot",
            lambda conn, *, account_id: snapshot,
        )

        _run_job(monkeypatch, tmp_path, RUN_ALL_FORCE_ARGS)
        payload = load_single_artifact_json(
            tmp_path / "local" / "artifacts",
            "monthly_governance_m1_risk_rebaseline_*.json",
        )
        acct = payload["accounts"][0]
        assert acct["snapshot_time"] == "2026-06-01T10:00:00"
        assert acct["kill_switch_triggered"] is False
        assert acct["gross_exposure"] == 50000.0


def test_main_returns_1_when_no_accounts(monkeypatch, tmp_path: Path, capsys) -> None:
    import trading.interfaces.runtime.jobs.job_runner._core as job_runner

    stub_runtime_job_basics(monkeypatch, module)
    monkeypatch.setattr(job_runner, "resolve_accounts", lambda *_args: [])

    assert _run_job(monkeypatch, tmp_path, RUN_ALL_FORCE_ARGS) == 1
    assert "No accounts specified." in capsys.readouterr().err


def test_missing_account_in_db_is_skipped(monkeypatch, tmp_path: Path) -> None:
    stub_runtime_job_basics(monkeypatch, module, account_lookup=lambda _name: None)

    assert _run_job(monkeypatch, tmp_path, RUN_ALL_FORCE_ARGS) == 0
    payload = load_single_artifact_json(
        tmp_path / "local" / "artifacts", "monthly_governance_m1_risk_rebaseline_*.json"
    )
    assert payload["accounts"] == []


def test_main_returns_1_when_snapshot_lookup_raises(monkeypatch, tmp_path: Path) -> None:
    stub_runtime_job_basics(monkeypatch, module)
    monkeypatch.setattr(
        module, "fetch_latest_risk_snapshot", lambda *_a, **_kw: (_ for _ in ()).throw(RuntimeError("boom"))
    )

    assert _run_job(monkeypatch, tmp_path, RUN_ALL_FORCE_ARGS) == 1


def test_monthly_risk_rebaseline_module_main_entrypoint(monkeypatch, tmp_path: Path) -> None:
    import trading.interfaces.runtime.jobs.job_runner._core as job_runner

    monkeypatch.setattr(job_runner, "load_account_names", lambda: [])
    monkeypatch.setattr(sys, "argv", ["m1_risk_rebaseline", "--repo-root", str(tmp_path)])

    with pytest.raises(SystemExit) as excinfo:
        run_module_as_main(module.__name__)

    assert excinfo.value.code == 1


def test_main_returns_1_when_account_resolution_fails(monkeypatch, tmp_path: Path, capsys) -> None:
    import trading.interfaces.runtime.jobs.job_runner._core as job_runner

    stub_runtime_job_basics(monkeypatch, module)
    monkeypatch.setattr(
        job_runner, "resolve_accounts", lambda *_args: (_ for _ in ()).throw(ValueError("bad accounts"))
    )

    assert _run_job(monkeypatch, tmp_path, RUN_ALL_FORCE_ARGS) == 1
    assert "bad accounts" in capsys.readouterr().err
