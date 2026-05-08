from __future__ import annotations

import datetime as dt
from pathlib import Path

import trading.interfaces.runtime.jobs.governance.monthly.m2_parameter_governance as module
from tests.support.runtime_jobs import (
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
        tag = module.month_tag(now)
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
        sleeve_row = {"id": 7, "name": "sleeve_q"}
        param_row = {"id": 42, "params_json": '{"lookback": 20, "threshold": 0.5}'}
        stub_runtime_job_basics(monkeypatch, module, sleeves_for_account=[sleeve_row])
        monkeypatch.setattr(
            module,
            "fetch_active_sleeve_strategy_assignment",
            lambda conn, *, sleeve_id: {"strategy_name": "mean_rev", "param_set_id": 42},
        )
        monkeypatch.setattr(
            module,
            "fetch_strategy_param_set_by_id",
            lambda conn, *, param_set_id: param_row,
        )

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
        sleeve_row = {"id": 7, "name": "sleeve_q"}
        param_row = {"id": 99, "params_json": '{"alpha": 1.2}'}
        captured: dict[str, int] = {}
        stub_runtime_job_basics(monkeypatch, module, sleeves_for_account=[sleeve_row])
        monkeypatch.setattr(
            module,
            "fetch_active_sleeve_strategy_assignment",
            lambda conn, *, sleeve_id: {"strategy_name": "mean_rev", "param_set_id": 99},
        )

        def _fetch_param_set_by_id(conn, *, param_set_id):
            captured["param_set_id"] = param_set_id
            return param_row

        monkeypatch.setattr(module, "fetch_strategy_param_set_by_id", _fetch_param_set_by_id)

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
        monkeypatch.setattr(
            module,
            "fetch_active_sleeve_strategy_assignment",
            lambda conn, *, sleeve_id: None,
        )

        _run_job(monkeypatch, tmp_path, RUN_ALL_FORCE_ARGS)
        payload = load_single_artifact_json(
            tmp_path / "local" / "artifacts",
            "monthly_governance_m2_parameter_governance_*.json",
        )
        sleeve = payload["accounts"][0]["sleeves"][0]
        assert sleeve["strategy_name"] is None
        assert sleeve["param_set_id"] is None
        assert sleeve["params"] is None
