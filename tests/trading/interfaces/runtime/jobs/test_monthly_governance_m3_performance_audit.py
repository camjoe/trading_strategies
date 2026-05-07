from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import trading.interfaces.runtime.jobs.governance.monthly.m3_performance_audit as module
from tests.support.runtime_jobs import run_runtime_job_main, stub_runtime_job_basics

MODULE_NAME = "trading.interfaces.runtime.jobs.governance.monthly.m3_performance_audit"
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
        log_path = logs_dir / f"monthly_governance_m3_performance_audit_{tag}_{timestamp}.log"
        log_path.write_text(f"{module.COMPLETE_SENTINEL}\n", encoding="utf-8")

        result = _run_job(monkeypatch, tmp_path)
        assert result == 0

    def test_returns_false_when_no_prior_log(self, tmp_path: Path) -> None:
        assert module.already_completed_this_month(tmp_path, "2099_12") is False

    def test_returns_true_when_sentinel_in_log(self, tmp_path: Path) -> None:
        tag = "2099_06"
        log = tmp_path / f"monthly_governance_m3_performance_audit_{tag}_20990601_000000.log"
        log.write_text(f"stuff\n{module.COMPLETE_SENTINEL}\n", encoding="utf-8")
        assert module.already_completed_this_month(tmp_path, tag) is True

    def test_returns_false_when_sentinel_absent(self, tmp_path: Path) -> None:
        tag = "2099_07"
        log = tmp_path / f"monthly_governance_m3_performance_audit_{tag}_20990701_000000.log"
        log.write_text("incomplete run\n", encoding="utf-8")
        assert module.already_completed_this_month(tmp_path, tag) is False


class TestArtifactStructure:
    def test_writes_artifact_with_correct_top_level_keys(self, monkeypatch, tmp_path: Path) -> None:
        stub_runtime_job_basics(monkeypatch, module, sleeves_for_account=[])

        result = _run_job(monkeypatch, tmp_path, RUN_ALL_FORCE_ARGS)
        assert result == 0

        artifacts = list(
            (tmp_path / "local" / "artifacts").glob("monthly_governance_m3_performance_audit_*.json")
        )
        assert len(artifacts) == 1
        payload = json.loads(artifacts[0].read_text(encoding="utf-8"))
        assert "month" in payload
        assert "generated_at" in payload
        assert "audit_window_days" in payload
        assert "accounts" in payload
        assert isinstance(payload["accounts"], list)

    def test_cumulative_return_and_stats_computed(self, monkeypatch, tmp_path: Path) -> None:
        sleeve_row = {"id": 5, "name": "sleeve_m"}
        # Two metric rows: +2% and +3%
        # compound = (1.02 * 1.03 - 1) * 100 = 5.06%
        metrics = [
            {
                "return_pct": 2.0,
                "drawdown_pct": -1.0,
                "hit_rate": 0.6,
                "trade_count": 3,
            },
            {
                "return_pct": 3.0,
                "drawdown_pct": -2.0,
                "hit_rate": 0.7,
                "trade_count": 4,
            },
        ]
        stub_runtime_job_basics(monkeypatch, module, sleeves_for_account=[sleeve_row])
        monkeypatch.setattr(
            module,
            "fetch_active_sleeve_strategy_assignment",
            lambda conn, *, sleeve_id: {"strategy_name": "trend_v2"},
        )
        monkeypatch.setattr(
            module,
            "fetch_daily_metrics_for_sleeve_window",
            lambda conn, *, sleeve_id, start_date, end_date: metrics,
        )

        result = _run_job(monkeypatch, tmp_path, RUN_ALL_FORCE_ARGS)
        assert result == 0

        artifacts = list(
            (tmp_path / "local" / "artifacts").glob("monthly_governance_m3_performance_audit_*.json")
        )
        payload = json.loads(artifacts[0].read_text(encoding="utf-8"))
        sleeve = payload["accounts"][0]["sleeves"][0]
        assert sleeve["sleeve_name"] == "sleeve_m"
        assert sleeve["strategy_name"] == "trend_v2"
        assert sleeve["data_points"] == 2
        assert sleeve["total_trades"] == 7
        assert sleeve["max_drawdown_pct"] == -2.0
        assert abs(sleeve["avg_hit_rate"] - 0.65) < 0.001
        # cumulative: (1.02 * 1.03 - 1) * 100 = 5.06
        assert abs(sleeve["cumulative_return_pct"] - 5.06) < 0.001

    def test_empty_metrics_produces_null_stats(self, monkeypatch, tmp_path: Path) -> None:
        sleeve_row = {"id": 9, "name": "sleeve_empty"}
        stub_runtime_job_basics(monkeypatch, module, sleeves_for_account=[sleeve_row])
        monkeypatch.setattr(
            module,
            "fetch_active_sleeve_strategy_assignment",
            lambda conn, *, sleeve_id: None,
        )
        monkeypatch.setattr(
            module,
            "fetch_daily_metrics_for_sleeve_window",
            lambda conn, *, sleeve_id, start_date, end_date: [],
        )

        _run_job(monkeypatch, tmp_path, RUN_ALL_FORCE_ARGS)
        artifacts = list(
            (tmp_path / "local" / "artifacts").glob("monthly_governance_m3_performance_audit_*.json")
        )
        payload = json.loads(artifacts[0].read_text(encoding="utf-8"))
        sleeve = payload["accounts"][0]["sleeves"][0]
        assert sleeve["data_points"] == 0
        assert sleeve["cumulative_return_pct"] is None
        assert sleeve["max_drawdown_pct"] is None
        assert sleeve["avg_hit_rate"] is None
        assert sleeve["total_trades"] == 0
        assert sleeve["strategy_name"] is None

    def test_audit_window_days_uses_inclusive_day_count(self, monkeypatch, tmp_path: Path) -> None:
        fixed_now = dt.datetime(2026, 1, 15, 9, 30, 0)

        class _FixedDateTime(dt.datetime):
            @classmethod
            def now(cls, tz=None):
                return fixed_now

        captured: dict[str, str] = {}
        sleeve_row = {"id": 5, "name": "sleeve_m"}
        monkeypatch.setattr(module.dt, "datetime", _FixedDateTime)
        stub_runtime_job_basics(monkeypatch, module, sleeves_for_account=[sleeve_row])
        monkeypatch.setattr(
            module,
            "fetch_active_sleeve_strategy_assignment",
            lambda conn, *, sleeve_id: None,
        )

        def _capture_metrics(conn, *, sleeve_id, start_date, end_date):
            captured["start_date"] = start_date
            captured["end_date"] = end_date
            return []

        monkeypatch.setattr(module, "fetch_daily_metrics_for_sleeve_window", _capture_metrics)

        result = _run_job(
            monkeypatch,
            tmp_path,
            (*RUN_ALL_FORCE_ARGS, "--audit-window-days", "1"),
        )
        assert result == 0
        assert captured["start_date"] == "2026-01-15"
        assert captured["end_date"] == "2026-01-15"
