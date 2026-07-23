from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest

import trading.interfaces.runtime.jobs.governance.monthly.m3_performance_audit as module
import trading.interfaces.runtime.jobs.job_runner._core as job_runner
from tests.src.trading.interfaces.helpers import run_module_as_main
from tests.src.trading.interfaces.runtime.jobs.loaders import (
    RUN_ALL_ACCOUNTS_ARGS,
    load_single_artifact_json,
    run_runtime_job_with_args,
    stub_runtime_job_basics,
    write_completed_runtime_log,
)
from trading.interfaces.runtime.jobs.job_helpers import month_tag

MODULE_NAME = "trading.interfaces.runtime.jobs.governance.monthly.m3_performance_audit"
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
            filename_prefix="monthly_governance_m3_performance_audit",
            tag=tag,
            sentinel=module.COMPLETE_SENTINEL,
        )

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
        stub_runtime_job_basics(monkeypatch, module, books_for_account=[])

        result = _run_job(monkeypatch, tmp_path, RUN_ALL_FORCE_ARGS)
        assert result == 0

        payload = load_single_artifact_json(
            tmp_path / "local" / "artifacts",
            "monthly_governance_m3_performance_audit_*.json",
        )
        assert "month" in payload
        assert "generated_at" in payload
        assert "audit_window_days" in payload
        assert "accounts" in payload
        assert isinstance(payload["accounts"], list)

    def test_cumulative_return_and_stats_computed(self, monkeypatch, tmp_path: Path) -> None:
        book_row = {"id": 5, "name": "book_m"}
        # Two metric rows: +2% and +3%
        # compound = (1.02 * 1.03 - 1) * 100 = 5.06%
        from types import SimpleNamespace as _NS

        metrics = [
            _NS(return_pct=2.0, drawdown_pct=-1.0, hit_rate=0.6, trade_count=3),
            _NS(return_pct=3.0, drawdown_pct=-2.0, hit_rate=0.7, trade_count=4),
        ]
        from types import SimpleNamespace as _NS

        stub_runtime_job_basics(
            monkeypatch,
            module,
            books_for_account=[(_NS(**book_row), _NS(strategy_name="trend_v2"))],
        )
        monkeypatch.setattr(
            module,
            "fetch_book_performance_window",
            lambda conn, *, book_id, start_date, end_date: metrics,
        )

        result = _run_job(monkeypatch, tmp_path, RUN_ALL_FORCE_ARGS)
        assert result == 0

        payload = load_single_artifact_json(
            tmp_path / "local" / "artifacts",
            "monthly_governance_m3_performance_audit_*.json",
        )
        book = payload["accounts"][0]["books"][0]
        assert book["book_name"] == "book_m"
        assert book["strategy_name"] == "trend_v2"
        assert book["data_points"] == 2
        assert book["total_trades"] == 7
        assert book["max_drawdown_pct"] == -2.0
        assert abs(book["avg_hit_rate"] - 0.65) < 0.001
        # cumulative: (1.02 * 1.03 - 1) * 100 = 5.06
        assert abs(book["cumulative_return_pct"] - 5.06) < 0.001

    def test_empty_metrics_produces_null_stats(self, monkeypatch, tmp_path: Path) -> None:
        book_row = {"id": 9, "name": "book_empty"}
        stub_runtime_job_basics(monkeypatch, module, books_for_account=[book_row])
        # unassigned book: the stubbed pair carries assignment=None
        monkeypatch.setattr(
            module,
            "fetch_book_performance_window",
            lambda conn, *, book_id, start_date, end_date: [],
        )

        _run_job(monkeypatch, tmp_path, RUN_ALL_FORCE_ARGS)
        payload = load_single_artifact_json(
            tmp_path / "local" / "artifacts",
            "monthly_governance_m3_performance_audit_*.json",
        )
        book = payload["accounts"][0]["books"][0]
        assert book["data_points"] == 0
        assert book["cumulative_return_pct"] is None
        assert book["max_drawdown_pct"] is None
        assert book["avg_hit_rate"] is None
        assert book["total_trades"] == 0
        assert book["strategy_name"] is None

    def test_audit_window_days_uses_inclusive_day_count(self, monkeypatch, tmp_path: Path) -> None:
        fixed_now = dt.datetime(2026, 1, 15, 9, 30, 0)

        class _FixedDateTime(dt.datetime):
            @classmethod
            def now(cls, tz=None):
                return fixed_now

        captured: dict[str, str] = {}
        book_row = {"id": 5, "name": "book_m"}
        # `now` is computed in the shared runner, so patch its datetime seam.
        monkeypatch.setattr(job_runner.dt, "datetime", _FixedDateTime)
        stub_runtime_job_basics(monkeypatch, module, books_for_account=[book_row])
        # unassigned book: the stubbed pair carries assignment=None

        def _capture_metrics(conn, *, book_id, start_date, end_date):
            captured["start_date"] = start_date
            captured["end_date"] = end_date
            return []

        monkeypatch.setattr(module, "fetch_book_performance_window", _capture_metrics)

        result = _run_job(
            monkeypatch,
            tmp_path,
            (*RUN_ALL_FORCE_ARGS, "--audit-window-days", "1"),
        )
        assert result == 0
        assert captured["start_date"] == "2026-01-15"
        assert captured["end_date"] == "2026-01-15"


def test_main_rejects_invalid_audit_window_days(monkeypatch, tmp_path: Path, capsys) -> None:
    assert _run_job(monkeypatch, tmp_path, (*RUN_ALL_FORCE_ARGS, "--audit-window-days", "0")) == 1
    assert "audit-window-days" in capsys.readouterr().err


def test_main_returns_1_when_no_accounts(monkeypatch, tmp_path: Path, capsys) -> None:
    stub_runtime_job_basics(monkeypatch, module)
    monkeypatch.setattr(job_runner, "resolve_accounts", lambda *_args: [])

    assert _run_job(monkeypatch, tmp_path, RUN_ALL_FORCE_ARGS) == 1
    assert "No accounts specified." in capsys.readouterr().err


def test_missing_account_in_db_is_skipped(monkeypatch, tmp_path: Path) -> None:
    stub_runtime_job_basics(monkeypatch, module, account_lookup=lambda _name: None)

    assert _run_job(monkeypatch, tmp_path, RUN_ALL_FORCE_ARGS) == 0
    payload = load_single_artifact_json(
        tmp_path / "local" / "artifacts", "monthly_governance_m3_performance_audit_*.json"
    )
    assert payload["accounts"] == []


def test_main_returns_1_when_metric_lookup_raises(monkeypatch, tmp_path: Path) -> None:
    stub_runtime_job_basics(monkeypatch, module)

    def _boom(conn, *, account_id):
        raise RuntimeError("boom")

    monkeypatch.setattr(module, "list_report_books", _boom)

    assert _run_job(monkeypatch, tmp_path, RUN_ALL_FORCE_ARGS) == 1


def test_monthly_performance_audit_module_main_entrypoint(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        sys, "argv", ["m3_performance_audit", "--repo-root", str(tmp_path), "--audit-window-days", "0"]
    )

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
