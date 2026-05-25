from __future__ import annotations

import datetime as dt
from pathlib import Path

from trading.domain.promotion_models import PromotionAssessment
import trading.interfaces.runtime.jobs.governance.weekly.w2_promotion_review as module
from tests.trading.interfaces.runtime.jobs.loaders import (
    RUN_ALL_ACCOUNTS_ARGS,
    load_single_artifact_json,
    run_runtime_job_with_args,
    stub_runtime_job_basics,
    write_completed_runtime_log,
)

MODULE_NAME = "trading.interfaces.runtime.jobs.governance.weekly.w2_promotion_review"
RUN_ALL_ARGS = RUN_ALL_ACCOUNTS_ARGS
RUN_ALL_FORCE_ARGS = (*RUN_ALL_ARGS, "--force-run")


def _run_job(monkeypatch, tmp_path: Path, args: tuple[str, ...] = RUN_ALL_ARGS) -> int:
    return run_runtime_job_with_args(monkeypatch, tmp_path, MODULE_NAME, args)


def _make_assessment(**overrides) -> PromotionAssessment:
    defaults: dict = {
        "ready_for_live": False,
        "blockers": [],
    }
    defaults.update(overrides)
    return PromotionAssessment(**defaults)


class TestDedupGuard:
    def test_skips_when_already_completed_this_week(self, monkeypatch, tmp_path: Path) -> None:
        now = dt.datetime.now()
        tag = module.week_tag(now)
        write_completed_runtime_log(
            tmp_path,
            filename_prefix="weekly_governance_w2_promotion_review",
            tag=tag,
            sentinel=module.COMPLETE_SENTINEL,
        )

        result = _run_job(monkeypatch, tmp_path)
        assert result == 0

    def test_returns_false_when_no_prior_log(self, tmp_path: Path) -> None:
        assert module.already_completed_this_week(tmp_path, "2099_W01") is False

    def test_returns_true_when_sentinel_in_log(self, tmp_path: Path) -> None:
        tag = "2099_W42"
        log = tmp_path / f"weekly_governance_w2_promotion_review_{tag}_20990101_000000.log"
        log.write_text(f"stuff\n{module.COMPLETE_SENTINEL}\n", encoding="utf-8")
        assert module.already_completed_this_week(tmp_path, tag) is True

    def test_returns_false_when_sentinel_absent(self, tmp_path: Path) -> None:
        tag = "2099_W43"
        log = tmp_path / f"weekly_governance_w2_promotion_review_{tag}_20990101_000000.log"
        log.write_text("incomplete run\n", encoding="utf-8")
        assert module.already_completed_this_week(tmp_path, tag) is False


class TestArtifactStructure:
    def test_writes_artifact_with_correct_top_level_keys(self, monkeypatch, tmp_path: Path) -> None:
        stub_runtime_job_basics(monkeypatch, module, sleeves_for_account=[])
        monkeypatch.setattr(
            module,
            "fetch_current_promotion_assessment",
            lambda conn, *, account_name: _make_assessment(),
        )

        result = _run_job(monkeypatch, tmp_path, RUN_ALL_FORCE_ARGS)
        assert result == 0

        payload = load_single_artifact_json(
            tmp_path / "local" / "artifacts",
            "weekly_governance_w2_promotion_review_*.json",
        )
        assert "week" in payload
        assert "generated_at" in payload
        assert "accounts" in payload
        assert isinstance(payload["accounts"], list)

    def test_artifact_account_fields_present(self, monkeypatch, tmp_path: Path) -> None:
        sleeve_row = {
            "id": 10,
            "name": "sleeve_alpha",
            "status": "active",
        }
        stub_runtime_job_basics(monkeypatch, module, sleeves_for_account=[sleeve_row])
        monkeypatch.setattr(
            module,
            "fetch_current_promotion_assessment",
            lambda conn, *, account_name: _make_assessment(ready_for_live=False, blockers=["missing_data"]),
        )
        monkeypatch.setattr(
            module,
            "fetch_active_sleeve_strategy_assignment",
            lambda conn, *, sleeve_id: {"strategy_name": "mean_rev"},
        )

        result = _run_job(monkeypatch, tmp_path, RUN_ALL_FORCE_ARGS)
        assert result == 0

        payload = load_single_artifact_json(
            tmp_path / "local" / "artifacts",
            "weekly_governance_w2_promotion_review_*.json",
        )
        acct = payload["accounts"][0]
        assert acct["account_name"] == "acct1"
        assert acct["ready_for_live"] is False
        assert acct["blockers"] == ["missing_data"]
        assert len(acct["sleeves"]) == 1
        assert acct["sleeves"][0]["sleeve_name"] == "sleeve_alpha"
        assert acct["sleeves"][0]["strategy_name"] == "mean_rev"
        assert acct["sleeves"][0]["sleeve_status"] == "active"
