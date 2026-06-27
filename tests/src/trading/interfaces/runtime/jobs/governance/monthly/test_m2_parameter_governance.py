from __future__ import annotations

import datetime as dt
from pathlib import Path
import sys
import pytest

import trading.interfaces.runtime.jobs.governance.monthly.m2_parameter_governance as module
import trading.interfaces.runtime.jobs.job_runner as job_runner
from trading.interfaces.runtime.jobs.job_helpers import month_tag
from tests.src.trading.interfaces.helpers import run_module_as_main
from tests.src.trading.interfaces.runtime.jobs.loaders import (
    RUN_ALL_ACCOUNTS_ARGS,
    load_single_artifact_json,
    run_runtime_job_with_args,
    stub_runtime_job_basics,
    write_completed_runtime_log,
)

MODULE_NAME = "trading.interfaces.runtime.jobs.governance.monthly.m2_parameter_governance"
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
            filename_prefix="monthly_governance_m2_parameter_governance",
            tag=tag,
            sentinel=module.COMPLETE_SENTINEL,
        )

        result = _run_job(monkeypatch, tmp_path)
        assert result == 0

    def test_returns_false_when_no_prior_log(self, tmp_path: Path) -> None:
        assert module.already_completed_this_month(tmp_path, "2099_12") is False

    def test_returns_true_when_sentinel_in_log(self, tmp_path: Path) -> None:
        tag = "2099_06"
        log = tmp_path / f"monthly_governance_m2_parameter_governance_{tag}_20990601_000000.log"
        log.write_text(f"stuff\n{module.COMPLETE_SENTINEL}\n", encoding="utf-8")
        assert module.already_completed_this_month(tmp_path, tag) is True

    def test_returns_false_when_sentinel_absent(self, tmp_path: Path) -> None:
        tag = "2099_07"
        log = tmp_path / f"monthly_governance_m2_parameter_governance_{tag}_20990701_000000.log"
        log.write_text("incomplete run\n", encoding="utf-8")
        assert module.already_completed_this_month(tmp_path, tag) is False


class TestArtifactStructure:
    def test_writes_artifact_with_correct_top_level_keys(self, monkeypatch, tmp_path: Path) -> None:
        stub_runtime_job_basics(monkeypatch, module, sleeves_for_account=[])

        result = _run_job(monkeypatch, tmp_path, RUN_ALL_FORCE_ARGS)
        assert result == 0

        payload = load_single_artifact_json(
            tmp_path / "local" / "artifacts",
            "monthly_governance_m2_parameter_governance_*.json",
        )
        assert "month" in payload
        assert "generated_at" in payload
        assert "accounts" in payload
        assert isinstance(payload["accounts"], list)

    def test_params_parsed_from_json_column(self, monkeypatch, tmp_path: Path) -> None:
        from types import SimpleNamespace as _NS

        sleeve_row = {"id": 7, "name": "sleeve_q"}
        mocks = stub_runtime_job_basics(monkeypatch, module, sleeves_for_account=[sleeve_row])
        mocks.sleeve_repo.fetch_active_assignment.return_value = _NS(strategy_name="mean_rev", param_set_id=42)
        mocks.param_set_repo.fetch_by_id.return_value = _NS(id=42, params_json='{"lookback": 20, "threshold": 0.5}')

        result = _run_job(monkeypatch, tmp_path, RUN_ALL_FORCE_ARGS)
        assert result == 0

        payload = load_single_artifact_json(
            tmp_path / "local" / "artifacts",
            "monthly_governance_m2_parameter_governance_*.json",
        )
        sleeve = payload["accounts"][0]["sleeves"][0]
        assert sleeve["sleeve_name"] == "sleeve_q"
        assert sleeve["strategy_name"] == "mean_rev"
        assert sleeve["param_set_id"] == 42
        assert sleeve["params"] == {"lookback": 20, "threshold": 0.5}

    def test_uses_assignment_param_set_id_instead_of_global_active_set(self, monkeypatch, tmp_path: Path) -> None:
        from types import SimpleNamespace as _NS

        sleeve_row = {"id": 7, "name": "sleeve_q"}
        captured: dict[str, int] = {}
        mocks = stub_runtime_job_basics(monkeypatch, module, sleeves_for_account=[sleeve_row])
        mocks.sleeve_repo.fetch_active_assignment.return_value = _NS(strategy_name="mean_rev", param_set_id=99)

        def _fetch_by_id(*, param_set_id):
            captured["param_set_id"] = param_set_id
            return _NS(id=99, params_json='{"alpha": 1.2}')

        mocks.param_set_repo.fetch_by_id.side_effect = _fetch_by_id

        result = _run_job(monkeypatch, tmp_path, RUN_ALL_FORCE_ARGS)
        assert result == 0
        assert captured["param_set_id"] == 99

        payload = load_single_artifact_json(
            tmp_path / "local" / "artifacts",
            "monthly_governance_m2_parameter_governance_*.json",
        )
        sleeve = payload["accounts"][0]["sleeves"][0]
        assert sleeve["param_set_id"] == 99
        assert sleeve["params"] == {"alpha": 1.2}

    def test_null_param_set_when_no_assignment(self, monkeypatch, tmp_path: Path) -> None:
        sleeve_row = {"id": 8, "name": "sleeve_r"}
        stub_runtime_job_basics(monkeypatch, module, sleeves_for_account=[sleeve_row])
        # fetch_active_assignment returns None by default from stub

        _run_job(monkeypatch, tmp_path, RUN_ALL_FORCE_ARGS)
        payload = load_single_artifact_json(
            tmp_path / "local" / "artifacts",
            "monthly_governance_m2_parameter_governance_*.json",
        )
        sleeve = payload["accounts"][0]["sleeves"][0]
        assert sleeve["strategy_name"] is None
        assert sleeve["param_set_id"] is None
        assert sleeve["params"] is None


def test_main_returns_1_when_no_accounts(monkeypatch, tmp_path: Path, capsys) -> None:
    stub_runtime_job_basics(monkeypatch, module)
    monkeypatch.setattr(job_runner, "resolve_accounts", lambda *_args: [])

    assert _run_job(monkeypatch, tmp_path, RUN_ALL_FORCE_ARGS) == 1
    assert "No accounts specified." in capsys.readouterr().err


def test_missing_account_in_db_is_skipped(monkeypatch, tmp_path: Path) -> None:
    stub_runtime_job_basics(monkeypatch, module, account_lookup=lambda _name: None)

    assert _run_job(monkeypatch, tmp_path, RUN_ALL_FORCE_ARGS) == 0
    payload = load_single_artifact_json(
        tmp_path / "local" / "artifacts", "monthly_governance_m2_parameter_governance_*.json"
    )
    assert payload["accounts"] == []


def test_invalid_params_json_falls_back_to_none(monkeypatch, tmp_path: Path) -> None:
    from types import SimpleNamespace as _NS

    sleeve_row = {"id": 7, "name": "sleeve_q"}
    mocks = stub_runtime_job_basics(monkeypatch, module, sleeves_for_account=[sleeve_row])
    mocks.sleeve_repo.fetch_active_assignment.return_value = _NS(strategy_name="mean_rev", param_set_id=42)
    mocks.param_set_repo.fetch_by_id.return_value = _NS(id=42, params_json="{bad json")

    assert _run_job(monkeypatch, tmp_path, RUN_ALL_FORCE_ARGS) == 0
    payload = load_single_artifact_json(
        tmp_path / "local" / "artifacts", "monthly_governance_m2_parameter_governance_*.json"
    )
    assert payload["accounts"][0]["sleeves"][0]["params"] is None


def test_main_returns_1_when_param_lookup_raises(monkeypatch, tmp_path: Path) -> None:
    from unittest.mock import MagicMock

    stub_runtime_job_basics(monkeypatch, module)
    boom_repo = MagicMock()
    boom_repo.fetch_for_account.side_effect = RuntimeError("boom")
    monkeypatch.setattr(module, "SleeveRepository", lambda conn: boom_repo)

    assert _run_job(monkeypatch, tmp_path, RUN_ALL_FORCE_ARGS) == 1


def test_monthly_parameter_governance_module_main_entrypoint(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(job_runner, "load_runtime_eligible_account_names", lambda: [])
    monkeypatch.setattr(sys, "argv", ["m2_parameter_governance", "--repo-root", str(tmp_path)])

    with pytest.raises(SystemExit) as excinfo:
        run_module_as_main(module.__name__)

    assert excinfo.value.code == 1


def test_main_returns_1_when_account_resolution_fails(monkeypatch, tmp_path: Path, capsys) -> None:
    stub_runtime_job_basics(monkeypatch, module)
    monkeypatch.setattr(job_runner, "resolve_accounts", lambda *_args: (_ for _ in ()).throw(ValueError("bad accounts")))

    assert _run_job(monkeypatch, tmp_path, RUN_ALL_FORCE_ARGS) == 1
    assert "bad accounts" in capsys.readouterr().err
