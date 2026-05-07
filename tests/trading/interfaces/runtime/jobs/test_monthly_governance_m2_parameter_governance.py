from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from types import SimpleNamespace

import trading.interfaces.runtime.jobs.monthly_governance_m2_parameter_governance as module
from tests.support.runtime_jobs import run_runtime_job_main

MODULE_NAME = "trading.interfaces.runtime.jobs.monthly_governance_m2_parameter_governance"


class TestDedupGuard:
    def test_skips_when_already_completed_this_month(self, monkeypatch, tmp_path: Path) -> None:
        now = dt.datetime.now()
        tag = module.month_tag(now)
        logs_dir = tmp_path / "local" / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        log_path = logs_dir / f"monthly_governance_m2_parameter_governance_{tag}_{timestamp}.log"
        log_path.write_text(f"{module.COMPLETE_SENTINEL}\n", encoding="utf-8")

        result = run_runtime_job_main(monkeypatch, tmp_path, MODULE_NAME, ["--accounts", "all"])
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
        mock_conn = SimpleNamespace(close=lambda: None)
        monkeypatch.setattr(module, "ensure_db", lambda: mock_conn)
        monkeypatch.setattr(module, "load_runtime_eligible_account_names", lambda: ["acct1"])
        monkeypatch.setattr(
            module,
            "fetch_account_by_name",
            lambda conn, name: SimpleNamespace(id=1, name=name),
        )
        monkeypatch.setattr(
            module,
            "fetch_strategy_sleeves_for_account",
            lambda conn, *, account_id: [],
        )

        result = run_runtime_job_main(
            monkeypatch, tmp_path, MODULE_NAME, ["--accounts", "all", "--force-run"]
        )
        assert result == 0

        artifacts = list(
            (tmp_path / "local" / "artifacts").glob("monthly_governance_m2_parameter_governance_*.json")
        )
        assert len(artifacts) == 1
        payload = json.loads(artifacts[0].read_text(encoding="utf-8"))
        assert "month" in payload
        assert "generated_at" in payload
        assert "accounts" in payload
        assert isinstance(payload["accounts"], list)

    def test_params_parsed_from_json_column(self, monkeypatch, tmp_path: Path) -> None:
        sleeve_row = {"id": 7, "name": "sleeve_q"}
        param_row = {"id": 42, "params_json": '{"lookback": 20, "threshold": 0.5}'}
        mock_conn = SimpleNamespace(close=lambda: None)
        monkeypatch.setattr(module, "ensure_db", lambda: mock_conn)
        monkeypatch.setattr(module, "load_runtime_eligible_account_names", lambda: ["acct1"])
        monkeypatch.setattr(
            module,
            "fetch_account_by_name",
            lambda conn, name: SimpleNamespace(id=1, name=name),
        )
        monkeypatch.setattr(
            module,
            "fetch_strategy_sleeves_for_account",
            lambda conn, *, account_id: [sleeve_row],
        )
        monkeypatch.setattr(
            module,
            "fetch_active_sleeve_strategy_assignment",
            lambda conn, *, sleeve_id: {"strategy_name": "mean_rev"},
        )
        monkeypatch.setattr(
            module,
            "fetch_active_strategy_param_set",
            lambda conn, *, strategy_name: param_row,
        )

        result = run_runtime_job_main(
            monkeypatch, tmp_path, MODULE_NAME, ["--accounts", "all", "--force-run"]
        )
        assert result == 0

        artifacts = list(
            (tmp_path / "local" / "artifacts").glob("monthly_governance_m2_parameter_governance_*.json")
        )
        payload = json.loads(artifacts[0].read_text(encoding="utf-8"))
        sleeve = payload["accounts"][0]["sleeves"][0]
        assert sleeve["sleeve_name"] == "sleeve_q"
        assert sleeve["strategy_name"] == "mean_rev"
        assert sleeve["param_set_id"] == 42
        assert sleeve["params"] == {"lookback": 20, "threshold": 0.5}

    def test_null_param_set_when_no_assignment(self, monkeypatch, tmp_path: Path) -> None:
        sleeve_row = {"id": 8, "name": "sleeve_r"}
        mock_conn = SimpleNamespace(close=lambda: None)
        monkeypatch.setattr(module, "ensure_db", lambda: mock_conn)
        monkeypatch.setattr(module, "load_runtime_eligible_account_names", lambda: ["acct1"])
        monkeypatch.setattr(
            module,
            "fetch_account_by_name",
            lambda conn, name: SimpleNamespace(id=1, name=name),
        )
        monkeypatch.setattr(
            module,
            "fetch_strategy_sleeves_for_account",
            lambda conn, *, account_id: [sleeve_row],
        )
        monkeypatch.setattr(
            module,
            "fetch_active_sleeve_strategy_assignment",
            lambda conn, *, sleeve_id: None,
        )

        run_runtime_job_main(
            monkeypatch, tmp_path, MODULE_NAME, ["--accounts", "all", "--force-run"]
        )
        artifacts = list(
            (tmp_path / "local" / "artifacts").glob("monthly_governance_m2_parameter_governance_*.json")
        )
        payload = json.loads(artifacts[0].read_text(encoding="utf-8"))
        sleeve = payload["accounts"][0]["sleeves"][0]
        assert sleeve["strategy_name"] is None
        assert sleeve["param_set_id"] is None
        assert sleeve["params"] is None
