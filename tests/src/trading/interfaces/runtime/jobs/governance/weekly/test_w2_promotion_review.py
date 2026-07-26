from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest

import trading.interfaces.runtime.jobs.governance.weekly.w2_promotion_review as module
import trading.interfaces.runtime.jobs.job_runner._core as job_runner
from tests.src.trading.interfaces.helpers import run_module_as_main
from tests.src.trading.interfaces.runtime.jobs.loaders import (
    RUN_ALL_ACCOUNTS_ARGS,
    load_single_artifact_json,
    run_runtime_job_with_args,
    stub_runtime_job_basics,
    write_completed_runtime_log,
)
from trading.interfaces.runtime.jobs.job_helpers import week_tag
from trading.models.promotion import PromotionAssessment

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
        tag = week_tag(now)
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
        stub_runtime_job_basics(monkeypatch, module, books_for_account=[])
        monkeypatch.setattr(
            module,
            "fetch_promotion_assessment",
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
        book_row = {
            "id": 10,
            "name": "book_alpha",
            "status": "active",
        }
        from types import SimpleNamespace as _NS

        stub_runtime_job_basics(
            monkeypatch,
            module,
            books_for_account=[(_NS(**book_row), _NS(strategy_name="mean_rev"))],
        )
        monkeypatch.setattr(
            module,
            "fetch_promotion_assessment",
            lambda conn, *, account_name: _make_assessment(ready_for_live=False, blockers=["missing_data"]),
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
        assert len(acct["books"]) == 1
        assert acct["books"][0]["book_name"] == "book_alpha"
        assert acct["books"][0]["strategy_name"] == "mean_rev"
        assert acct["books"][0]["book_status"] == "active"


def test_main_returns_1_when_no_accounts(monkeypatch, tmp_path: Path, capsys) -> None:
    stub_runtime_job_basics(monkeypatch, module)
    monkeypatch.setattr(job_runner, "resolve_accounts", lambda *_args: [])

    assert _run_job(monkeypatch, tmp_path, RUN_ALL_FORCE_ARGS) == 1
    assert "No accounts specified." in capsys.readouterr().err


def test_missing_account_in_db_is_skipped(monkeypatch, tmp_path: Path) -> None:
    stub_runtime_job_basics(monkeypatch, module, account_lookup=lambda _name: None)

    assert _run_job(monkeypatch, tmp_path, RUN_ALL_FORCE_ARGS) == 0
    payload = load_single_artifact_json(
        tmp_path / "local" / "artifacts", "weekly_governance_w2_promotion_review_*.json"
    )
    assert payload["accounts"] == []


def test_main_returns_1_when_assessment_lookup_raises(monkeypatch, tmp_path: Path) -> None:
    stub_runtime_job_basics(monkeypatch, module)
    monkeypatch.setattr(
        module, "fetch_promotion_assessment", lambda *_a, **_kw: (_ for _ in ()).throw(RuntimeError("boom"))
    )

    assert _run_job(monkeypatch, tmp_path, RUN_ALL_FORCE_ARGS) == 1


def test_weekly_promotion_review_module_main_entrypoint(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(job_runner, "load_runtime_eligible_account_names", lambda: [])
    monkeypatch.setattr(sys, "argv", ["w2_promotion_review", "--repo-root", str(tmp_path)])

    with pytest.raises(SystemExit) as excinfo:
        run_module_as_main(module.__name__)

    assert excinfo.value.code == 1


def test_main_returns_1_when_account_resolution_fails(monkeypatch, tmp_path: Path, capsys) -> None:
    stub_runtime_job_basics(monkeypatch, module)
    monkeypatch.setattr(
        job_runner, "resolve_accounts", lambda *_args: (_ for _ in ()).throw(ValueError("bad accounts"))
    )

    assert _run_job(monkeypatch, tmp_path, RUN_ALL_FORCE_ARGS) == 1
    assert "bad accounts" in capsys.readouterr().err
