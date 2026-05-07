from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from types import SimpleNamespace

import trading.interfaces.runtime.jobs.weekly_governance_w1_leaderboard as module
from tests.support.runtime_jobs import run_runtime_job_main

MODULE_NAME = "trading.interfaces.runtime.jobs.weekly_governance_w1_leaderboard"


class TestDedupGuard:
    def test_skips_when_already_completed_this_week(self, monkeypatch, tmp_path: Path) -> None:
        now = dt.datetime.now()
        tag = module.week_tag(now)
        logs_dir = tmp_path / "local" / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        log_path = logs_dir / f"weekly_governance_w1_leaderboard_{tag}_{timestamp}.log"
        log_path.write_text(f"{module.COMPLETE_SENTINEL}\n", encoding="utf-8")

        result = run_runtime_job_main(monkeypatch, tmp_path, MODULE_NAME, ["--accounts", "all"])
        assert result == 0

    def test_returns_false_when_no_prior_log(self, tmp_path: Path) -> None:
        assert module.already_completed_this_week(tmp_path, "2099_W01") is False

    def test_returns_true_when_sentinel_in_log(self, tmp_path: Path) -> None:
        tag = "2099_W42"
        log = tmp_path / f"weekly_governance_w1_leaderboard_{tag}_20990101_000000.log"
        log.write_text(f"stuff\n{module.COMPLETE_SENTINEL}\n", encoding="utf-8")
        assert module.already_completed_this_week(tmp_path, tag) is True

    def test_returns_false_when_sentinel_absent(self, tmp_path: Path) -> None:
        tag = "2099_W43"
        log = tmp_path / f"weekly_governance_w1_leaderboard_{tag}_20990101_000000.log"
        log.write_text("incomplete run\n", encoding="utf-8")
        assert module.already_completed_this_week(tmp_path, tag) is False


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

        artifacts = list((tmp_path / "local" / "artifacts").glob("weekly_governance_w1_leaderboard_*.json"))
        assert len(artifacts) == 1
        payload = json.loads(artifacts[0].read_text(encoding="utf-8"))
        assert "week" in payload
        assert "generated_at" in payload
        assert "window_days" in payload
        assert "accounts" in payload
        assert isinstance(payload["accounts"], list)
        assert payload["accounts"][0]["account_name"] == "acct1"
        assert payload["accounts"][0]["sleeves"] == []

    def test_sleeve_ranking_included_in_artifact(self, monkeypatch, tmp_path: Path) -> None:
        sleeve_row = {
            "id": 10,
            "name": "sleeve_a",
        }
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
            lambda conn, *, sleeve_id: {"strategy_name": "trend_follow"},
        )
        monkeypatch.setattr(
            module,
            "fetch_daily_metrics_for_sleeve_window",
            lambda conn, *, sleeve_id, start_date, end_date: [
                {
                    "return_pct": 1.5,
                    "risk_adjusted_score": 0.8,
                    "drawdown_pct": -2.0,
                    "trade_count": 5,
                }
            ],
        )

        result = run_runtime_job_main(
            monkeypatch, tmp_path, MODULE_NAME, ["--accounts", "all", "--force-run"]
        )
        assert result == 0

        artifacts = list((tmp_path / "local" / "artifacts").glob("weekly_governance_w1_leaderboard_*.json"))
        payload = json.loads(artifacts[0].read_text(encoding="utf-8"))
        sleeve = payload["accounts"][0]["sleeves"][0]
        assert sleeve["rank"] == 1
        assert sleeve["sleeve_name"] == "sleeve_a"
        assert sleeve["strategy_name"] == "trend_follow"
        assert sleeve["data_points"] == 1
