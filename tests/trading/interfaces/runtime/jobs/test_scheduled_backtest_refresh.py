from __future__ import annotations

import importlib
import json
import types
from pathlib import Path


def _load():
    return importlib.import_module("trading.interfaces.runtime.jobs.scheduled_backtest_refresh")


def _args(**overrides):
    defaults = {
        "accounts": "all",
        "force_run": False,
        "run_source": "test-run",
        "enable_run": True,
        "max_attempts": 2,
        "backoff_seconds": 0.0,
        "tickers_file": "tickers.txt",
        "universe_history_dir": None,
        "start": None,
        "end": None,
        "lookback_months": 6,
        "slippage_bps": 5.0,
        "fee": 0.0,
        "run_name_prefix": "scheduled_refresh",
        "allow_approximate_leaps": False,
        "repo_root": ".",
    }
    defaults.update(overrides)
    return types.SimpleNamespace(**defaults)


def test_already_completed_today_detects_sentinel(tmp_path: Path):
    module = _load()
    day_tag = "20260414"
    log = tmp_path / f"scheduled_backtest_refresh_{day_tag}_010101.log"
    log.write_text(f"anything\n{module.COMPLETE_SENTINEL}\n", encoding="utf-8")

    assert module.already_completed_today(tmp_path, day_tag) is True


def test_retry_delay_seconds_doubles_each_attempt():
    module = _load()

    assert module.retry_delay_seconds(2.0, 1) == 2.0
    assert module.retry_delay_seconds(2.0, 2) == 4.0
    assert module.retry_delay_seconds(2.0, 3) == 8.0


def test_build_backtest_command_includes_optional_settings():
    module = _load()
    args = _args(
        tickers_file="local/tickers.txt",
        universe_history_dir="local/history",
        start="2025-01-01",
        end="2025-12-31",
        lookback_months=None,
        allow_approximate_leaps=True,
        fee=1.25,
    )

    command = module.build_backtest_command(account="acct1", args=args, day_tag="20260414")

    assert command[:5] == ["-m", "trading.interfaces.cli.main", "backtest", "--account", "acct1"]
    assert "--universe-history-dir" in command
    assert "--start" in command
    assert "--end" in command
    assert "--allow-approximate-leaps" in command


def test_extract_run_id_returns_integer_when_present():
    assert _load().extract_run_id("Backtest complete: run_id=42 account=acct") == 42


def test_extract_run_id_returns_none_when_absent():
    assert _load().extract_run_id("Backtest completed without summary") is None


def test_run_backtest_refresh_with_retry_retries_transient_then_succeeds(tmp_path: Path):
    module = _load()
    calls: list[tuple[str, list[str]]] = []
    sleeps: list[float] = []
    responses = [
        (1, "temporary failure while fetching market data; try again"),
        (0, "Backtest complete: run_id=77 account=acct1"),
    ]

    def fake_run_command(log_path, label, args, cwd):
        calls.append((label, args))
        return responses.pop(0)

    result = module.run_backtest_refresh_with_retry(
        log_path=tmp_path / "run.log",
        repo_root=tmp_path,
        account="acct1",
        args=_args(backoff_seconds=1.5, max_attempts=3),
        day_tag="20260414",
        run_command_fn=fake_run_command,
        sleep_fn=sleeps.append,
    )

    assert result["status"] == "success"
    assert result["attempts"] == 2
    assert result["run_id"] == 77
    assert len(calls) == 2
    assert sleeps == [1.5]


def test_run_backtest_refresh_with_retry_fails_when_run_id_missing(tmp_path: Path):
    module = _load()

    def fake_run_command(_log_path, _label, _args, _cwd):
        return 0, "Backtest complete but summary changed"

    result = module.run_backtest_refresh_with_retry(
        log_path=tmp_path / "run.log",
        repo_root=tmp_path,
        account="acct1",
        args=_args(max_attempts=1),
        day_tag="20260414",
        run_command_fn=fake_run_command,
        sleep_fn=lambda _seconds: None,
    )

    assert result["status"] == "failed"
    assert result["error"] == "missing_run_id"
    assert result["run_id"] is None


def test_is_run_enabled_true_when_flag_set(monkeypatch):
    module = _load()
    monkeypatch.delenv(module.BACKTEST_REFRESH_ENABLED_ENV, raising=False)

    assert module.is_run_enabled(_args(enable_run=True)) is True


def test_is_run_enabled_true_when_env_set(monkeypatch):
    module = _load()
    monkeypatch.setenv(module.BACKTEST_REFRESH_ENABLED_ENV, "true")

    assert module.is_run_enabled(_args(enable_run=False)) is True


def test_is_run_enabled_false_by_default(monkeypatch):
    module = _load()
    monkeypatch.delenv(module.BACKTEST_REFRESH_ENABLED_ENV, raising=False)

    assert module.is_run_enabled(_args(enable_run=False)) is False


def test_main_uses_module_level_repo_paths(monkeypatch, tmp_path: Path):
    module = _load()
    monkeypatch.setattr(module, "parse_args", lambda: _args(repo_root=str(tmp_path)))
    monkeypatch.setattr(module, "load_all_account_names", lambda: ["acct1"])
    monkeypatch.setattr(module, "already_completed_today", lambda _log_dir, _day_tag: False)
    monkeypatch.setattr(
        module,
        "run_backtest_refresh_with_retry",
        lambda **_kwargs: {
            "account": "acct1",
            "status": "success",
            "attempts": 1,
            "run_id": 88,
            "started_at": "2026-04-14T00:00:00+00:00",
            "finished_at": "2026-04-14T00:00:01+00:00",
            "last_exit_code": 0,
        },
    )

    assert module.main() == 0

    artifacts = list((tmp_path / "local" / "exports" / "scheduled_backtest_refresh").glob("scheduled_backtest_refresh_*.json"))
    assert len(artifacts) == 1
    payload = json.loads(artifacts[0].read_text(encoding="utf-8"))
    assert Path(payload["log_path"]).parts[0] == "local"
    assert payload["results"][0]["run_id"] == 88


def test_main_skips_duplicate_runs(monkeypatch, tmp_path: Path, capsys):
    module = _load()
    monkeypatch.setattr(module, "parse_args", lambda: _args(repo_root=str(tmp_path)))
    monkeypatch.setattr(module, "load_all_account_names", lambda: ["acct1"])
    monkeypatch.setattr(module, "already_completed_today", lambda _log_dir, _day_tag: True)

    assert module.main() == 0
    assert "skipping duplicate run" in capsys.readouterr().out.lower()


def test_main_returns_1_for_unknown_account(monkeypatch, tmp_path: Path, capsys):
    module = _load()
    monkeypatch.setattr(module, "parse_args", lambda: _args(repo_root=str(tmp_path), accounts="ghost"))
    monkeypatch.setattr(module, "load_all_account_names", lambda: ["acct1"])

    assert module.main() == 1
    assert "Unknown account" in capsys.readouterr().err
