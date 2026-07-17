from __future__ import annotations

import contextlib
import datetime as dt
import sys
import types
from pathlib import Path

import pytest

import trading.interfaces.runtime.jobs.job_runner._core as job_runner
from trading.interfaces.runtime.jobs.job_helpers import day_tag
from tests.src.trading.interfaces.helpers import run_module_as_main
from tests.src.trading.interfaces.runtime.jobs.loaders import (
    DAILY_BACKTEST_REFRESH_MODULE as MODULE_NAME,
    daily_backtest_refresh as module,
    load_single_artifact_json,
    run_runtime_job_with_args,
    write_completed_runtime_log,
)

ENABLE_ARGS = ("--enable-run",)
ENABLE_FORCE_ARGS = ("--enable-run", "--force-run")
EXPORTS_DIR_PARTS = ("local", "exports", "daily_backtest_refresh")
ARTIFACT_GLOB = "daily_backtest_refresh_*.json"


def _run(monkeypatch, tmp_path: Path, args: tuple[str, ...]) -> int:
    return run_runtime_job_with_args(monkeypatch, tmp_path, MODULE_NAME, args)


def _stub_accounts(monkeypatch, accounts: list[str]) -> None:
    monkeypatch.setattr(job_runner, "load_runtime_eligible_account_names", lambda: list(accounts))


def _stub_db(monkeypatch) -> None:
    # The targeted job opens the DB in-process (open_db=True) to enumerate targets.
    @contextlib.contextmanager
    def _fake_session():
        yield object()

    monkeypatch.setattr(job_runner, "db_session", _fake_session)


def _stub_one_target_per_account(monkeypatch, *, strategy: str = "macd") -> None:
    monkeypatch.setattr(
        module,
        "find_stale_backtests",
        lambda _conn, *, account_name, threshold_days: [
            types.SimpleNamespace(
                account_name=account_name, account_id=1, strategy_name=strategy, age_days=None, reason="missing"
            )
        ],
    )


def _target_success(run_id: int = 88) -> dict[str, object]:
    return {"account": "acct1", "status": "success", "attempts": 1, "run_id": run_id, "strategy": "macd"}


def _target_failed() -> dict[str, object]:
    return {"account": "acct1", "status": "failed", "attempts": 2, "run_id": None, "strategy": "macd"}


class TestValidation:
    def test_rejects_non_positive_max_attempts(self, monkeypatch, tmp_path: Path, capsys) -> None:
        assert _run(monkeypatch, tmp_path, ("--enable-run", "--max-attempts", "0")) == 1
        assert "max-attempts" in capsys.readouterr().err

    def test_rejects_negative_backoff(self, monkeypatch, tmp_path: Path, capsys) -> None:
        assert _run(monkeypatch, tmp_path, ("--enable-run", "--backoff-seconds", "-1.0")) == 1
        assert "backoff-seconds" in capsys.readouterr().err


class TestEnableGate:
    def test_returns_0_when_disabled(self, monkeypatch, tmp_path: Path, capsys) -> None:
        monkeypatch.delenv(module.BACKTEST_REFRESH_ENABLED_ENV, raising=False)
        assert _run(monkeypatch, tmp_path, ()) == 0
        assert "disabled" in capsys.readouterr().err

    def test_enabled_via_env(self, monkeypatch, tmp_path: Path) -> None:
        monkeypatch.setenv(module.BACKTEST_REFRESH_ENABLED_ENV, "true")
        _stub_accounts(monkeypatch, ["acct1"])
        _stub_db(monkeypatch)
        _stub_one_target_per_account(monkeypatch)
        monkeypatch.setattr(module, "run_target_backtest_with_retry", lambda **_kwargs: _target_success())
        assert _run(monkeypatch, tmp_path, ("--force-run",)) == 0


class TestAccountResolution:
    def test_returns_1_for_unknown_account(self, monkeypatch, tmp_path: Path, capsys) -> None:
        _stub_accounts(monkeypatch, ["acct1"])
        assert _run(monkeypatch, tmp_path, ("--enable-run", "--accounts", "ghost")) == 1
        assert "Unknown account" in capsys.readouterr().err

    def test_returns_1_when_no_accounts_after_resolution(self, monkeypatch, tmp_path: Path, capsys) -> None:
        _stub_accounts(monkeypatch, ["acct1"])
        monkeypatch.setattr(job_runner, "resolve_accounts", lambda *_a: [])
        assert _run(monkeypatch, tmp_path, ENABLE_ARGS) == 1
        assert "No accounts specified." in capsys.readouterr().err


class TestDedupGuard:
    def test_skips_duplicate_runs(self, monkeypatch, tmp_path: Path, capsys) -> None:
        _stub_accounts(monkeypatch, ["acct1"])
        write_completed_runtime_log(
            tmp_path,
            filename_prefix="daily_backtest_refresh",
            tag=day_tag(dt.datetime.now()),
            sentinel=module.COMPLETE_SENTINEL,
        )

        assert _run(monkeypatch, tmp_path, ENABLE_ARGS) == 0
        assert "skipping duplicate run" in capsys.readouterr().out.lower()


class TestAccountLoop:
    def test_success_writes_artifact_with_per_target_run_id(self, monkeypatch, tmp_path: Path) -> None:
        _stub_accounts(monkeypatch, ["acct1"])
        _stub_db(monkeypatch)
        _stub_one_target_per_account(monkeypatch)
        monkeypatch.setattr(module, "run_target_backtest_with_retry", lambda **_kwargs: _target_success(run_id=88))

        assert _run(monkeypatch, tmp_path, ENABLE_FORCE_ARGS) == 0

        payload = load_single_artifact_json(tmp_path.joinpath(*EXPORTS_DIR_PARTS), ARTIFACT_GLOB)
        assert Path(payload["log_path"]).parts[0] == "local"
        account_result = payload["results"][0]
        assert account_result["account"] == "acct1"
        assert account_result["targets"] == 1
        assert account_result["results"][0]["run_id"] == 88
        assert account_result["results"][0]["strategy"] == "macd"

    def test_no_stale_targets_is_a_clean_success(self, monkeypatch, tmp_path: Path) -> None:
        _stub_accounts(monkeypatch, ["acct1"])
        _stub_db(monkeypatch)
        monkeypatch.setattr(module, "find_stale_backtests", lambda _conn, **_kw: [])
        monkeypatch.setattr(
            module,
            "run_target_backtest_with_retry",
            lambda **_kwargs: (_ for _ in ()).throw(AssertionError("must not run when nothing is stale")),
        )

        assert _run(monkeypatch, tmp_path, ENABLE_FORCE_ARGS) == 0
        payload = load_single_artifact_json(tmp_path.joinpath(*EXPORTS_DIR_PARTS), ARTIFACT_GLOB)
        assert payload["results"][0]["targets"] == 0

    def test_stops_on_first_failed_refresh(self, monkeypatch, tmp_path: Path) -> None:
        accounts_seen: list[str] = []
        _stub_accounts(monkeypatch, ["acct1", "acct2"])
        _stub_db(monkeypatch)

        def _find(_conn, *, account_name, threshold_days):
            accounts_seen.append(account_name)
            return [
                types.SimpleNamespace(
                    account_name=account_name, account_id=1, strategy_name="macd", age_days=None, reason="missing"
                )
            ]

        monkeypatch.setattr(module, "find_stale_backtests", _find)
        monkeypatch.setattr(module, "run_target_backtest_with_retry", lambda **_kwargs: _target_failed())

        assert _run(monkeypatch, tmp_path, ENABLE_FORCE_ARGS) == 1
        assert accounts_seen == ["acct1"]  # stopped after the first account failed

    def test_run_meta_reflects_passed_args(self, monkeypatch, tmp_path: Path) -> None:
        _stub_accounts(monkeypatch, ["acct1"])
        _stub_db(monkeypatch)
        _stub_one_target_per_account(monkeypatch)
        monkeypatch.setattr(module, "run_target_backtest_with_retry", lambda **_kwargs: _target_success())

        assert (
            _run(
                monkeypatch,
                tmp_path,
                (*ENABLE_FORCE_ARGS, "--tickers-file", "tickers.txt", "--allow-approximate-leaps"),
            )
            == 0
        )

        payload = load_single_artifact_json(tmp_path.joinpath(*EXPORTS_DIR_PARTS), ARTIFACT_GLOB)
        assert payload["tickers_file"] == "tickers.txt"
        assert payload["allow_approximate_leaps"] is True
        assert payload["stale_threshold_days"] == 3


def test_backtest_refresh_module_main_entrypoint(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv(module.BACKTEST_REFRESH_ENABLED_ENV, raising=False)
    monkeypatch.setattr(sys, "argv", ["backtest_refresh", "--repo-root", str(tmp_path)])

    with pytest.raises(SystemExit) as excinfo:
        run_module_as_main(module.__name__)

    assert excinfo.value.code == 0
