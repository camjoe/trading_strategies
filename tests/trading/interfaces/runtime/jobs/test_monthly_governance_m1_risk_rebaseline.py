from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import trading.interfaces.runtime.jobs.governance.monthly.m1_risk_rebaseline as module
from tests.support.runtime_jobs import run_runtime_job_main, stub_runtime_job_basics

MODULE_NAME = "trading.interfaces.runtime.jobs.governance.monthly.m1_risk_rebaseline"
RUN_ALL_ARGS = ("--accounts", "all")
RUN_ALL_FORCE_ARGS = (*RUN_ALL_ARGS, "--force-run")


def _run_job(monkeypatch, tmp_path: Path, args: tuple[str, ...] = RUN_ALL_ARGS) -> int:
    return run_runtime_job_main(monkeypatch, tmp_path, MODULE_NAME, list(args))


class TestDedupGuard:
    def test_skips_when_already_completed_this_month(self, monkeypatch, tmp_path: Path) -> None:
        now = dt.datetime.now()
        tag = module.month_tag(now)
        logs_dir = tmp_path / "local" / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        log_path = logs_dir / f"monthly_governance_m1_risk_rebaseline_{tag}_{timestamp}.log"
        log_path.write_text(f"{module.COMPLETE_SENTINEL}\n", encoding="utf-8")

        result = _run_job(monkeypatch, tmp_path)
        assert result == 0

    def test_returns_false_when_no_prior_log(self, tmp_path: Path) -> None:
        assert module.already_completed_this_month(tmp_path, "2099_12") is False

    def test_returns_true_when_sentinel_in_log(self, tmp_path: Path) -> None:
        tag = "2099_06"
        log = tmp_path / f"monthly_governance_m1_risk_rebaseline_{tag}_20990601_000000.log"
        log.write_text(f"stuff\n{module.COMPLETE_SENTINEL}\n", encoding="utf-8")
        assert module.already_completed_this_month(tmp_path, tag) is True

    def test_returns_false_when_sentinel_absent(self, tmp_path: Path) -> None:
        tag = "2099_07"
        log = tmp_path / f"monthly_governance_m1_risk_rebaseline_{tag}_20990701_000000.log"
        log.write_text("incomplete run\n", encoding="utf-8")
        assert module.already_completed_this_month(tmp_path, tag) is False


class TestArtifactStructure:
    def test_writes_artifact_with_correct_top_level_keys(self, monkeypatch, tmp_path: Path) -> None:
        stub_runtime_job_basics(monkeypatch, module)
        monkeypatch.setattr(
            module,
            "fetch_latest_portfolio_risk_snapshot",
            lambda conn, *, account_id: None,
        )

        result = _run_job(monkeypatch, tmp_path, RUN_ALL_FORCE_ARGS)
        assert result == 0

        artifacts = list(
            (tmp_path / "local" / "artifacts").glob("monthly_governance_m1_risk_rebaseline_*.json")
        )
        assert len(artifacts) == 1
        payload = json.loads(artifacts[0].read_text(encoding="utf-8"))
        assert "month" in payload
        assert "generated_at" in payload
        assert "accounts" in payload
        assert isinstance(payload["accounts"], list)

    def test_no_snapshot_produces_null_entry(self, monkeypatch, tmp_path: Path) -> None:
        stub_runtime_job_basics(monkeypatch, module)
        monkeypatch.setattr(
            module,
            "fetch_latest_portfolio_risk_snapshot",
            lambda conn, *, account_id: None,
        )

        _run_job(monkeypatch, tmp_path, RUN_ALL_FORCE_ARGS)
        artifacts = list(
            (tmp_path / "local" / "artifacts").glob("monthly_governance_m1_risk_rebaseline_*.json")
        )
        payload = json.loads(artifacts[0].read_text(encoding="utf-8"))
        acct = payload["accounts"][0]
        assert acct["account_name"] == "acct1"
        assert acct["snapshot_time"] is None
        assert "note" in acct

    def test_snapshot_fields_present_when_snapshot_exists(self, monkeypatch, tmp_path: Path) -> None:
        snapshot = {
            "snapshot_time": "2026-06-01T10:00:00",
            "gross_exposure": 50000.0,
            "net_exposure": 30000.0,
            "drawdown_pct": -3.5,
            "daily_loss_pct": -1.2,
            "kill_switch_triggered": 0,
            "max_symbol_concentration_pct": 15.0,
            "max_sector_concentration_pct": 30.0,
        }
        stub_runtime_job_basics(monkeypatch, module)
        monkeypatch.setattr(
            module,
            "fetch_latest_portfolio_risk_snapshot",
            lambda conn, *, account_id: snapshot,
        )

        _run_job(monkeypatch, tmp_path, RUN_ALL_FORCE_ARGS)
        artifacts = list(
            (tmp_path / "local" / "artifacts").glob("monthly_governance_m1_risk_rebaseline_*.json")
        )
        payload = json.loads(artifacts[0].read_text(encoding="utf-8"))
        acct = payload["accounts"][0]
        assert acct["snapshot_time"] == "2026-06-01T10:00:00"
        assert acct["kill_switch_triggered"] is False
        assert acct["gross_exposure"] == 50000.0
