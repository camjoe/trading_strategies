from __future__ import annotations

import contextlib
import datetime as dt
import sys
from pathlib import Path

import pytest

import trading.interfaces.runtime.jobs.job_runner._core as job_runner
from trading.interfaces.runtime.jobs.job_helpers import day_tag
from trading.models.rotation.rotation_strategy_metrics import RotationStrategyMetrics
from trading.services.books.challenger_evaluation import ChallengerEvaluationRun, BookChallengerEvaluation
from tests.src.trading.interfaces.helpers import run_module_as_main
from tests.src.trading.interfaces.runtime.jobs.loaders import (
    DAILY_CHALLENGER_SHADOW_EVAL_MODULE as MODULE_NAME,
    daily_challenger_shadow_eval as module,
    load_single_artifact_json,
    run_runtime_job_main,
    write_completed_runtime_log,
)

EXPORT_DIR_PARTS = ("local", "exports", "daily_challenger_shadow_eval")
ARTIFACT_GLOB = "daily_challenger_shadow_eval_*.json"


def _run(monkeypatch, tmp_path: Path, args: list[str]) -> int:
    return run_runtime_job_main(monkeypatch, tmp_path, MODULE_NAME, args)


def _stub_accounts(monkeypatch, accounts: list[str]) -> None:
    monkeypatch.setattr(job_runner, "load_runtime_eligible_account_names", lambda: list(accounts))


def _stub_db(monkeypatch) -> None:
    @contextlib.contextmanager
    def _fake_session():
        yield object()

    monkeypatch.setattr(job_runner, "db_session", _fake_session)


def _sample_run(account_name: str) -> ChallengerEvaluationRun:
    return ChallengerEvaluationRun(
        account_id=1,
        account_name=account_name,
        books=[
            BookChallengerEvaluation(
                book_id=77,
                incumbent_strategy="trend",
                rolling_window_days=30,
                window_start_day="2026-04-08",
                window_end_day="2026-05-07",
                incumbent=RotationStrategyMetrics(
                    strategy_name="trend",
                    trade_count=15,
                    risk_adjusted_return=0.5,
                    stability=0.0,
                    drawdown_penalty=0.0,
                    cost_penalty=0.0,
                    regime_fit=0.0,
                ),
                challengers=[
                    RotationStrategyMetrics(
                        strategy_name="meanrev",
                        trade_count=12,
                        risk_adjusted_return=0.9,
                        stability=0.58,
                        drawdown_penalty=0.4,
                        cost_penalty=0.0,
                        regime_fit=0.0,
                    )
                ],
            )
        ],
    )


def test_main_returns_0_when_disabled(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.delenv(module.CHALLENGER_SHADOW_EVAL_ENABLED_ENV, raising=False)
    assert _run(monkeypatch, tmp_path, []) == 0
    assert "disabled" in capsys.readouterr().err


def test_main_returns_1_for_invalid_window(monkeypatch, tmp_path: Path, capsys) -> None:
    assert _run(monkeypatch, tmp_path, ["--enable-run", "--rolling-window-days", "0"]) == 1
    assert "rolling-window-days" in capsys.readouterr().err


def test_main_writes_success_artifact(monkeypatch, tmp_path: Path) -> None:
    _stub_accounts(monkeypatch, ["acct1"])
    _stub_db(monkeypatch)
    monkeypatch.setattr(
        module,
        "run_shadow_eval_for_account",
        lambda _conn, *, account_name, rolling_window_days, as_of_iso: _sample_run(account_name),
    )

    assert _run(monkeypatch, tmp_path, ["--accounts", "acct1", "--enable-run"]) == 0

    payload = load_single_artifact_json(tmp_path.joinpath(*EXPORT_DIR_PARTS), ARTIFACT_GLOB)
    assert payload["status"] == "success"
    assert payload["results"][0]["account_name"] == "acct1"
    assert payload["results"][0]["books"][0]["challenger_count"] == 1


def test_main_returns_1_for_unknown_account(monkeypatch, tmp_path: Path, capsys) -> None:
    _stub_accounts(monkeypatch, ["acct1"])
    assert _run(monkeypatch, tmp_path, ["--accounts", "ghost", "--enable-run"]) == 1
    assert "Unknown account" in capsys.readouterr().err


def test_main_returns_1_when_no_accounts(monkeypatch, tmp_path: Path, capsys) -> None:
    _stub_accounts(monkeypatch, ["acct1"])
    monkeypatch.setattr(job_runner, "resolve_accounts", lambda *_args: [])
    assert _run(monkeypatch, tmp_path, ["--enable-run"]) == 1
    assert "No accounts specified." in capsys.readouterr().err


def test_main_skips_duplicate_run_and_writes_skipped_artifact(monkeypatch, tmp_path: Path) -> None:
    _stub_accounts(monkeypatch, ["acct1"])
    write_completed_runtime_log(
        tmp_path,
        filename_prefix="daily_challenger_shadow_eval",
        tag=day_tag(dt.datetime.now()),
        sentinel=module.COMPLETE_SENTINEL,
    )

    assert _run(monkeypatch, tmp_path, ["--enable-run"]) == 0

    payload = load_single_artifact_json(tmp_path.joinpath(*EXPORT_DIR_PARTS), ARTIFACT_GLOB)
    assert payload["status"] == "skipped"
    assert payload["results"] == []


def test_main_writes_failure_artifact_when_eval_raises(monkeypatch, tmp_path: Path) -> None:
    _stub_accounts(monkeypatch, ["acct1"])
    _stub_db(monkeypatch)
    monkeypatch.setattr(
        module, "run_shadow_eval_for_account", lambda *_a, **_kw: (_ for _ in ()).throw(RuntimeError("boom"))
    )

    assert _run(monkeypatch, tmp_path, ["--enable-run"]) == 1

    payload = load_single_artifact_json(tmp_path.joinpath(*EXPORT_DIR_PARTS), ARTIFACT_GLOB)
    assert payload["status"] == "failed"
    assert payload["error"] == "boom"


def test_main_registered_in_support_module_constant() -> None:
    assert MODULE_NAME.endswith("daily.challenger_shadow_eval")


def test_run_shadow_eval_for_account_uses_account_lookup_and_builder(monkeypatch) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(module, "get_account", lambda _conn, name: {"name": name})

    def _fake_builder(_conn, *, account, as_of_iso, rolling_window_days):
        captured["account"] = account
        captured["as_of_iso"] = as_of_iso
        captured["rolling_window_days"] = rolling_window_days
        return "shadow-run"

    monkeypatch.setattr(module, "build_book_challenger_evaluations", _fake_builder)

    result = module.run_shadow_eval_for_account(
        object(), account_name="acct1", rolling_window_days=45, as_of_iso="2026-05-07"
    )

    assert result == "shadow-run"
    assert captured == {"account": {"name": "acct1"}, "as_of_iso": "2026-05-07", "rolling_window_days": 45}


def test_challenger_shadow_eval_module_main_entrypoint(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv(module.CHALLENGER_SHADOW_EVAL_ENABLED_ENV, raising=False)
    monkeypatch.setattr(sys, "argv", ["challenger_shadow_eval", "--repo-root", str(tmp_path)])

    with pytest.raises(SystemExit) as excinfo:
        run_module_as_main(module.__name__)

    assert excinfo.value.code == 0
