from __future__ import annotations

import datetime as dt
from pathlib import Path

import trading.interfaces.runtime.jobs.governance.weekly.w3_allocation_review as module
from tests.support.runtime_jobs import (
    RUN_ALL_ACCOUNTS_ARGS,
    load_single_artifact_json,
    run_runtime_job_with_args,
    stub_runtime_job_basics,
    write_completed_runtime_log,
)

MODULE_NAME = "trading.interfaces.runtime.jobs.governance.weekly.w3_allocation_review"
RUN_ALL_ARGS = RUN_ALL_ACCOUNTS_ARGS
RUN_ALL_FORCE_ARGS = (*RUN_ALL_ARGS, "--force-run")


def _run_job(monkeypatch, tmp_path: Path, args: tuple[str, ...] = RUN_ALL_ARGS) -> int:
    return run_runtime_job_with_args(monkeypatch, tmp_path, MODULE_NAME, args)


class TestDedupGuard:
    def test_skips_when_already_completed_this_week(self, monkeypatch, tmp_path: Path) -> None:
        now = dt.datetime.now()
        tag = module.week_tag(now)
        write_completed_runtime_log(
            tmp_path,
            filename_prefix="weekly_governance_w3_allocation_review",
            tag=tag,
            sentinel=module.COMPLETE_SENTINEL,
        )

        result = _run_job(monkeypatch, tmp_path)
        assert result == 0

    def test_returns_false_when_no_prior_log(self, tmp_path: Path) -> None:
        assert module.already_completed_this_week(tmp_path, "2099_W01") is False

    def test_returns_true_when_sentinel_in_log(self, tmp_path: Path) -> None:
        tag = "2099_W42"
        log = tmp_path / f"weekly_governance_w3_allocation_review_{tag}_20990101_000000.log"
        log.write_text(f"stuff\n{module.COMPLETE_SENTINEL}\n", encoding="utf-8")
        assert module.already_completed_this_week(tmp_path, tag) is True

    def test_returns_false_when_sentinel_absent(self, tmp_path: Path) -> None:
        tag = "2099_W43"
        log = tmp_path / f"weekly_governance_w3_allocation_review_{tag}_20990101_000000.log"
        log.write_text("incomplete run\n", encoding="utf-8")
        assert module.already_completed_this_week(tmp_path, tag) is False


class TestArtifactStructure:
    def test_writes_artifact_with_correct_top_level_keys(self, monkeypatch, tmp_path: Path) -> None:
        stub_runtime_job_basics(monkeypatch, module, sleeves_for_account=[])

        result = _run_job(monkeypatch, tmp_path, RUN_ALL_FORCE_ARGS)
        assert result == 0

        payload = load_single_artifact_json(
            tmp_path / "local" / "artifacts",
            "weekly_governance_w3_allocation_review_*.json",
        )
        assert "week" in payload
        assert "generated_at" in payload
        assert "drift_threshold_pct" in payload
        assert "accounts" in payload
        assert isinstance(payload["accounts"], list)

    def test_drift_and_reweight_computed_correctly(self, monkeypatch, tmp_path: Path) -> None:
        # Two sleeves: start_equity 600 and 400 (60% / 40% target)
        # current_equity values: 600 and 400 (60% / 40% current)
        sleeve_rows = [
            {
                "id": 1,
                "name": "sleeve_a",
                "start_equity": 600.0,
                "current_cash": 100.0,
                "current_equity": 600.0,
            },
            {
                "id": 2,
                "name": "sleeve_b",
                "start_equity": 400.0,
                "current_cash": 100.0,
                "current_equity": 400.0,
            },
        ]
        stub_runtime_job_basics(monkeypatch, module, sleeves_for_account=sleeve_rows)

        result = _run_job(
            monkeypatch,
            tmp_path,
            (*RUN_ALL_FORCE_ARGS, "--drift-threshold-pct", "5.0"),
        )
        assert result == 0

        payload = load_single_artifact_json(
            tmp_path / "local" / "artifacts",
            "weekly_governance_w3_allocation_review_*.json",
        )
        acct = payload["accounts"][0]
        assert acct["total_nav"] == 1000.0  # 600 + 400
        sleeves = {s["sleeve_name"]: s for s in acct["sleeves"]}
        # sleeve_a: current_nav=600, current_pct=60, target_pct=60, drift=0 → no reweight
        assert abs(sleeves["sleeve_a"]["current_pct"] - 60.0) < 0.01
        assert abs(sleeves["sleeve_a"]["target_pct"] - 60.0) < 0.01
        assert abs(sleeves["sleeve_a"]["drift_pct"] - 0.0) < 0.01
        assert sleeves["sleeve_a"]["reweight_suggested"] is False
        # sleeve_b: current_nav=400, current_pct=40, target_pct=40, drift=0 → no reweight
        assert abs(sleeves["sleeve_b"]["current_pct"] - 40.0) < 0.01
        assert abs(sleeves["sleeve_b"]["target_pct"] - 40.0) < 0.01
        assert abs(sleeves["sleeve_b"]["drift_pct"] - 0.0) < 0.01
        assert sleeves["sleeve_b"]["reweight_suggested"] is False
