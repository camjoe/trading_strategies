from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest

import trading.interfaces.runtime.jobs.governance.monthly.m2_parameter_governance as module
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

MODULE_NAME = "trading.interfaces.runtime.jobs.governance.monthly.m2_parameter_governance"
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
            filename_prefix="monthly_governance_m2_parameter_governance",
            tag=tag,
            sentinel=module.COMPLETE_SENTINEL,
        )

        result = _run_job(monkeypatch, tmp_path)
        assert result == 0


class TestArtifactStructure:
    def test_writes_artifact_with_correct_top_level_keys(self, monkeypatch, tmp_path: Path) -> None:
        stub_runtime_job_basics(monkeypatch, module, books_for_account=[])

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

    def test_params_reported_from_catalog(self, monkeypatch, tmp_path: Path) -> None:
        from types import SimpleNamespace as _NS

        book_row = {"id": 7, "name": "book_q"}
        stub_runtime_job_basics(
            monkeypatch,
            module,
            books_for_account=[(_NS(**book_row), _NS(strategy_name="mean_rev"))],
        )
        captured: dict[str, str] = {}

        def _resolve(_conn, strategy_key):
            captured["strategy_key"] = strategy_key
            return _NS(primitive="mean_reversion", params={"window": 20, "band_pct": 0.5})

        monkeypatch.setattr(module, "resolve_catalog_strategy", _resolve)

        result = _run_job(monkeypatch, tmp_path, RUN_ALL_FORCE_ARGS)
        assert result == 0
        assert captured["strategy_key"] == "mean_rev"

        payload = load_single_artifact_json(
            tmp_path / "local" / "artifacts",
            "monthly_governance_m2_parameter_governance_*.json",
        )
        book = payload["accounts"][0]["books"][0]
        assert book["book_name"] == "book_q"
        assert book["strategy_name"] == "mean_rev"
        assert book["primitive"] == "mean_reversion"
        assert book["params"] == {"window": 20, "band_pct": 0.5}

    def test_no_params_when_no_assignment(self, monkeypatch, tmp_path: Path) -> None:
        book_row = {"id": 8, "name": "book_r"}
        stub_runtime_job_basics(monkeypatch, module, books_for_account=[book_row])
        # unassigned book: the stubbed pair carries assignment=None

        _run_job(monkeypatch, tmp_path, RUN_ALL_FORCE_ARGS)
        payload = load_single_artifact_json(
            tmp_path / "local" / "artifacts",
            "monthly_governance_m2_parameter_governance_*.json",
        )
        book = payload["accounts"][0]["books"][0]
        assert book["strategy_name"] is None
        assert book["primitive"] is None
        assert book["params"] is None


def test_main_returns_1_when_no_accounts(monkeypatch, tmp_path: Path, capsys) -> None:
    stub_runtime_job_basics(monkeypatch, module)
    monkeypatch.setattr(job_runner, "resolve_accounts", lambda *_args: [])

    assert _run_job(monkeypatch, tmp_path, RUN_ALL_FORCE_ARGS) == 1
    assert "No accounts specified." in capsys.readouterr().err


def test_missing_account_in_db_is_skipped(monkeypatch, tmp_path: Path) -> None:
    stub_runtime_job_basics(monkeypatch, module, account_lookup=lambda _name: None)

    assert _run_job(monkeypatch, tmp_path, RUN_ALL_FORCE_ARGS) == 0
    payload = load_single_artifact_json(
        tmp_path / "local" / "artifacts", "monthly_governance_m2_parameter_governance_*.json"
    )
    assert payload["accounts"] == []


def test_unresolvable_strategy_falls_back_to_none(monkeypatch, tmp_path: Path) -> None:
    from types import SimpleNamespace as _NS

    book_row = {"id": 7, "name": "book_q"}
    stub_runtime_job_basics(
        monkeypatch,
        module,
        books_for_account=[(_NS(**book_row), _NS(strategy_name="mean_rev"))],
    )

    def _resolve(_conn, _strategy_key):
        raise module.UnknownCatalogStrategyError("no catalog row")

    monkeypatch.setattr(module, "resolve_catalog_strategy", _resolve)

    assert _run_job(monkeypatch, tmp_path, RUN_ALL_FORCE_ARGS) == 0
    payload = load_single_artifact_json(
        tmp_path / "local" / "artifacts", "monthly_governance_m2_parameter_governance_*.json"
    )
    assert payload["accounts"][0]["books"][0]["params"] is None


def test_main_returns_1_when_param_lookup_raises(monkeypatch, tmp_path: Path) -> None:
    stub_runtime_job_basics(monkeypatch, module)

    def _boom(conn, *, account_id):
        raise RuntimeError("boom")

    monkeypatch.setattr(module, "list_report_books", _boom)

    assert _run_job(monkeypatch, tmp_path, RUN_ALL_FORCE_ARGS) == 1


def test_monthly_parameter_governance_module_main_entrypoint(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(job_runner, "load_runtime_eligible_account_names", lambda: [])
    monkeypatch.setattr(sys, "argv", ["m2_parameter_governance", "--repo-root", str(tmp_path)])

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
