from __future__ import annotations

import datetime as dt
from pathlib import Path
import sys
import pytest

import trading.interfaces.runtime.jobs.governance.weekly.w1_leaderboard as module
from tests.trading.interfaces.helpers import run_module_as_main
from tests.trading.interfaces.runtime.jobs.loaders import (
    RUN_ALL_ACCOUNTS_ARGS,
    load_single_artifact_json,
    run_runtime_job_with_args,
    stub_runtime_job_basics,
    write_completed_runtime_log,
)

MODULE_NAME = "trading.interfaces.runtime.jobs.governance.weekly.w1_leaderboard"
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
            filename_prefix="weekly_governance_w1_leaderboard",
            tag=tag,
            sentinel=module.COMPLETE_SENTINEL,
        )

        result = _run_job(monkeypatch, tmp_path)
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
        stub_runtime_job_basics(monkeypatch, module, sleeves_for_account=[])

        result = _run_job(monkeypatch, tmp_path, RUN_ALL_FORCE_ARGS)
        assert result == 0

        payload = load_single_artifact_json(
            tmp_path / "local" / "artifacts",
            "weekly_governance_w1_leaderboard_*.json",
        )
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
        stub_runtime_job_basics(monkeypatch, module, sleeves_for_account=[sleeve_row])
        monkeypatch.setattr(
            module,
            "fetch_active_sleeve_strategy_assignment",
            lambda conn, *, sleeve_id: {"strategy_name": "trend_follow"},
        )
        monkeypatch.setattr(
            module,
            "fetch_sleeve_performance_window",
            lambda conn, *, sleeve_id, start_date, end_date: [
                {
                    "return_pct": 1.5,
                    "risk_adjusted_score": 0.8,
                    "drawdown_pct": -2.0,
                    "trade_count": 5,
                }
            ],
        )

        result = _run_job(monkeypatch, tmp_path, RUN_ALL_FORCE_ARGS)
        assert result == 0

        payload = load_single_artifact_json(
            tmp_path / "local" / "artifacts",
            "weekly_governance_w1_leaderboard_*.json",
        )
        sleeve = payload["accounts"][0]["sleeves"][0]
        assert sleeve["rank"] == 1
        assert sleeve["sleeve_name"] == "sleeve_a"
        assert sleeve["strategy_name"] == "trend_follow"
        assert sleeve["data_points"] == 1

    def test_window_days_uses_inclusive_day_count(self, monkeypatch, tmp_path: Path) -> None:
        fixed_now = dt.datetime(2026, 1, 15, 9, 30, 0)

        class _FixedDateTime(dt.datetime):
            @classmethod
            def now(cls, tz=None):
                return fixed_now

        captured: dict[str, str] = {}
        sleeve_row = {"id": 10, "name": "sleeve_a"}
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

        monkeypatch.setattr(module, "fetch_sleeve_performance_window", _capture_metrics)

        result = _run_job(
            monkeypatch,
            tmp_path,
            (*RUN_ALL_FORCE_ARGS, "--window-days", "1"),
        )
        assert result == 0
        assert captured["start_date"] == "2026-01-15"
        assert captured["end_date"] == "2026-01-15"


def test_main_rejects_invalid_window_days(monkeypatch, tmp_path: Path, capsys) -> None:
    result = _run_job(monkeypatch, tmp_path, (*RUN_ALL_FORCE_ARGS, "--window-days", "0"))
    assert result == 1
    assert "window-days" in capsys.readouterr().err


def test_main_returns_1_when_no_accounts(monkeypatch, tmp_path: Path, capsys) -> None:
    stub_runtime_job_basics(monkeypatch, module)
    monkeypatch.setattr(module, "resolve_accounts", lambda *_args: [])

    assert _run_job(monkeypatch, tmp_path, RUN_ALL_FORCE_ARGS) == 1
    assert "No accounts specified." in capsys.readouterr().err


def test_missing_account_in_db_is_skipped(monkeypatch, tmp_path: Path) -> None:
    stub_runtime_job_basics(monkeypatch, module, account_lookup=lambda _name: None)

    assert _run_job(monkeypatch, tmp_path, RUN_ALL_FORCE_ARGS) == 0
    payload = load_single_artifact_json(tmp_path / "local" / "artifacts", "weekly_governance_w1_leaderboard_*.json")
    assert payload["accounts"] == []


def test_main_returns_1_when_repository_lookup_raises(monkeypatch, tmp_path: Path) -> None:
    stub_runtime_job_basics(monkeypatch, module)
    monkeypatch.setattr(
        module, "fetch_strategy_sleeves_for_account", lambda *_a, **_kw: (_ for _ in ()).throw(RuntimeError("boom"))
    )

    assert _run_job(monkeypatch, tmp_path, RUN_ALL_FORCE_ARGS) == 1


def test_weekly_leaderboard_module_main_entrypoint(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(sys, "argv", ["w1_leaderboard", "--repo-root", str(tmp_path), "--window-days", "0"])

    with pytest.raises(SystemExit) as excinfo:
        run_module_as_main(module.__name__)

    assert excinfo.value.code == 1


def test_main_returns_1_when_account_resolution_fails(monkeypatch, tmp_path: Path, capsys) -> None:
    stub_runtime_job_basics(monkeypatch, module)
    monkeypatch.setattr(module, "resolve_accounts", lambda *_args: (_ for _ in ()).throw(ValueError("bad accounts")))

    assert _run_job(monkeypatch, tmp_path, RUN_ALL_FORCE_ARGS) == 1
    assert "bad accounts" in capsys.readouterr().err
