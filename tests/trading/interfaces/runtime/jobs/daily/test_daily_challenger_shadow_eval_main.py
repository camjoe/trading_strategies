from __future__ import annotations

from pathlib import Path

import sys
import pytest

from trading.domain.sleeve_rotation import SleeveStrategyMetrics
from trading.services.sleeves.shadow_evaluation import ShadowEvaluationRun, SleeveShadowEvaluation
from tests.trading.interfaces.helpers import run_module_as_main
from tests.trading.interfaces.runtime.jobs.loaders import (
    DAILY_CHALLENGER_SHADOW_EVAL_MODULE,
    daily_challenger_shadow_eval as module,
    load_single_artifact_json,
    make_daily_challenger_shadow_eval_args,
    run_runtime_job_main,
    set_runtime_eligible_accounts,
)


def test_is_run_enabled_true_when_flag_set(monkeypatch) -> None:
    monkeypatch.delenv(module.CHALLENGER_SHADOW_EVAL_ENABLED_ENV, raising=False)
    assert module.is_run_enabled(make_daily_challenger_shadow_eval_args(enable_run=True)) is True


def test_is_run_enabled_true_when_env_set(monkeypatch) -> None:
    monkeypatch.setenv(module.CHALLENGER_SHADOW_EVAL_ENABLED_ENV, "true")
    assert module.is_run_enabled(make_daily_challenger_shadow_eval_args(enable_run=False)) is True


def test_is_run_enabled_false_by_default(monkeypatch) -> None:
    monkeypatch.delenv(module.CHALLENGER_SHADOW_EVAL_ENABLED_ENV, raising=False)
    assert module.is_run_enabled(make_daily_challenger_shadow_eval_args(enable_run=False)) is False


def test_main_returns_0_when_disabled(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.delenv(module.CHALLENGER_SHADOW_EVAL_ENABLED_ENV, raising=False)
    assert run_runtime_job_main(monkeypatch, tmp_path, DAILY_CHALLENGER_SHADOW_EVAL_MODULE, []) == 0
    assert "disabled" in capsys.readouterr().err


def test_main_returns_1_for_invalid_window(monkeypatch, tmp_path: Path, capsys) -> None:
    assert (
        run_runtime_job_main(
            monkeypatch,
            tmp_path,
            DAILY_CHALLENGER_SHADOW_EVAL_MODULE,
            ["--enable-run", "--rolling-window-days", "0"],
        )
        == 1
    )
    assert "rolling-window-days" in capsys.readouterr().err


def test_main_writes_success_artifact(monkeypatch, tmp_path: Path) -> None:
    set_runtime_eligible_accounts(monkeypatch, DAILY_CHALLENGER_SHADOW_EVAL_MODULE, ["acct1"])
    monkeypatch.setattr(module, "already_completed_today", lambda _log_dir, _day_tag: False)
    monkeypatch.setattr(module, "ts", lambda: "2026-05-07T12:00:00+00:00")
    monkeypatch.setattr(module, "day_tag", lambda _now: "20260507")
    monkeypatch.setattr(
        module,
        "run_shadow_eval_for_account",
        lambda _conn, *, account_name, rolling_window_days, as_of_iso: ShadowEvaluationRun(
            account_id=1,
            account_name=account_name,
            window_start_day="2026-04-08",
            window_end_day="2026-05-07",
            sleeves=[
                SleeveShadowEvaluation(
                    sleeve_id=10,
                    incumbent_strategy="trend",
                    challengers=[
                        SleeveStrategyMetrics(
                            strategy_name="meanrev",
                            param_set_id=22,
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
        ),
    )

    class _Conn:
        def close(self):
            return None

    monkeypatch.setattr(module, "ensure_db", lambda: _Conn())

    assert (
        run_runtime_job_main(
            monkeypatch,
            tmp_path,
            DAILY_CHALLENGER_SHADOW_EVAL_MODULE,
            ["--accounts", "acct1", "--enable-run"],
        )
        == 0
    )
    payload = load_single_artifact_json(
        tmp_path / "local" / "exports" / "daily_challenger_shadow_eval",
        "daily_challenger_shadow_eval_*.json",
    )
    assert payload["status"] == "success"
    assert payload["results"][0]["account_name"] == "acct1"
    assert payload["results"][0]["sleeves"][0]["challenger_count"] == 1


def test_main_returns_1_for_unknown_account(monkeypatch, tmp_path: Path, capsys) -> None:
    set_runtime_eligible_accounts(monkeypatch, DAILY_CHALLENGER_SHADOW_EVAL_MODULE, ["acct1"])

    assert (
        run_runtime_job_main(
            monkeypatch,
            tmp_path,
            DAILY_CHALLENGER_SHADOW_EVAL_MODULE,
            ["--accounts", "ghost", "--enable-run"],
        )
        == 1
    )
    assert "Unknown account" in capsys.readouterr().err


def test_main_registered_in_support_module_constant() -> None:
    assert DAILY_CHALLENGER_SHADOW_EVAL_MODULE.endswith("daily.challenger_shadow_eval")


def test_already_completed_today_detects_sentinel(tmp_path: Path) -> None:
    log = tmp_path / "daily_challenger_shadow_eval_20260507_120000.log"
    log.write_text(f"ok\n{module.COMPLETE_SENTINEL}\n", encoding="utf-8")

    assert module.already_completed_today(tmp_path, "20260507") is True


def test_run_shadow_eval_for_account_uses_account_lookup_and_builder(monkeypatch) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(module, "get_account", lambda _conn, name: {"name": name})

    def _fake_builder(_conn, *, account, as_of_iso, rolling_window_days):
        captured["account"] = account
        captured["as_of_iso"] = as_of_iso
        captured["rolling_window_days"] = rolling_window_days
        return "shadow-run"

    monkeypatch.setattr(module, "build_sleeve_shadow_evaluation", _fake_builder)

    result = module.run_shadow_eval_for_account(
        object(), account_name="acct1", rolling_window_days=45, as_of_iso="2026-05-07"
    )

    assert result == "shadow-run"
    assert captured == {"account": {"name": "acct1"}, "as_of_iso": "2026-05-07", "rolling_window_days": 45}


def test_main_returns_1_when_no_accounts(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.setattr(module, "parse_args", lambda: make_daily_challenger_shadow_eval_args(repo_root=str(tmp_path)))
    monkeypatch.setattr(module, "resolve_accounts", lambda *_args: [])
    monkeypatch.setattr(module, "load_runtime_eligible_account_names", lambda: ["acct1"])

    assert module.main() == 1
    assert "No accounts specified." in capsys.readouterr().err


def test_main_skips_duplicate_run_and_writes_skipped_artifact(monkeypatch, tmp_path: Path) -> None:
    set_runtime_eligible_accounts(monkeypatch, DAILY_CHALLENGER_SHADOW_EVAL_MODULE, ["acct1"])
    monkeypatch.setattr(module, "already_completed_today", lambda _log_dir, _day_tag: True)

    assert run_runtime_job_main(monkeypatch, tmp_path, DAILY_CHALLENGER_SHADOW_EVAL_MODULE, ["--enable-run"]) == 0

    payload = load_single_artifact_json(
        tmp_path / "local" / "exports" / "daily_challenger_shadow_eval",
        "daily_challenger_shadow_eval_*.json",
    )
    assert payload["status"] == "skipped"
    assert payload["results"] == []


def test_main_writes_failure_artifact_when_eval_raises(monkeypatch, tmp_path: Path) -> None:
    set_runtime_eligible_accounts(monkeypatch, DAILY_CHALLENGER_SHADOW_EVAL_MODULE, ["acct1"])
    monkeypatch.setattr(module, "already_completed_today", lambda _log_dir, _day_tag: False)
    monkeypatch.setattr(
        module, "run_shadow_eval_for_account", lambda *_a, **_kw: (_ for _ in ()).throw(RuntimeError("boom"))
    )

    class _Conn:
        def close(self):
            return None

    monkeypatch.setattr(module, "ensure_db", lambda: _Conn())

    assert run_runtime_job_main(monkeypatch, tmp_path, DAILY_CHALLENGER_SHADOW_EVAL_MODULE, ["--enable-run"]) == 1

    payload = load_single_artifact_json(
        tmp_path / "local" / "exports" / "daily_challenger_shadow_eval",
        "daily_challenger_shadow_eval_*.json",
    )
    assert payload["status"] == "failed"
    assert payload["error"] == "boom"


def test_challenger_shadow_eval_module_main_entrypoint(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(sys, "argv", ["challenger_shadow_eval", "--repo-root", str(tmp_path)])

    with pytest.raises(SystemExit) as excinfo:
        run_module_as_main(module.__name__)

    assert excinfo.value.code == 0
