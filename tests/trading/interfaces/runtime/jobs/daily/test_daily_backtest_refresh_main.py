from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock

from tests.support.runtime_jobs import daily_backtest_refresh as module, make_daily_backtest_refresh_args


def test_is_run_enabled_true_when_flag_set(monkeypatch) -> None:
    monkeypatch.delenv(module.BACKTEST_REFRESH_ENABLED_ENV, raising=False)
    assert module.is_run_enabled(make_daily_backtest_refresh_args(enable_run=True)) is True


def test_is_run_enabled_true_when_env_set(monkeypatch) -> None:
    monkeypatch.setenv(module.BACKTEST_REFRESH_ENABLED_ENV, "true")
    assert module.is_run_enabled(make_daily_backtest_refresh_args(enable_run=False)) is True


def test_is_run_enabled_false_by_default(monkeypatch) -> None:
    monkeypatch.delenv(module.BACKTEST_REFRESH_ENABLED_ENV, raising=False)
    assert module.is_run_enabled(make_daily_backtest_refresh_args(enable_run=False)) is False


def test_main_uses_module_level_repo_paths(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(module, "parse_args", lambda: make_daily_backtest_refresh_args(repo_root=str(tmp_path)))
    monkeypatch.setattr(module, "load_runtime_eligible_account_names", lambda: ["acct1"])
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

    artifacts = list((tmp_path / "local" / "exports" / "daily_backtest_refresh").glob("daily_backtest_refresh_*.json"))
    assert len(artifacts) == 1
    payload = json.loads(artifacts[0].read_text(encoding="utf-8"))
    assert Path(payload["log_path"]).parts[0] == "local"
    assert payload["results"][0]["run_id"] == 88


def test_main_skips_duplicate_runs(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.setattr(module, "parse_args", lambda: make_daily_backtest_refresh_args(repo_root=str(tmp_path)))
    monkeypatch.setattr(module, "load_runtime_eligible_account_names", lambda: ["acct1"])
    monkeypatch.setattr(module, "already_completed_today", lambda _log_dir, _day_tag: True)

    assert module.main() == 0
    assert "skipping duplicate run" in capsys.readouterr().out.lower()


def test_main_returns_1_for_unknown_account(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.setattr(
        module, "parse_args", lambda: make_daily_backtest_refresh_args(repo_root=str(tmp_path), accounts="ghost")
    )
    monkeypatch.setattr(module, "load_runtime_eligible_account_names", lambda: ["acct1"])

    assert module.main() == 1
    assert "Unknown account" in capsys.readouterr().err


def test_main_returns_0_when_disabled(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.setattr(
        module, "parse_args", lambda: make_daily_backtest_refresh_args(repo_root=str(tmp_path), enable_run=False)
    )
    monkeypatch.setattr(module, "is_run_enabled", lambda _args: False)

    assert module.main() == 0
    assert "disabled" in capsys.readouterr().err


def test_main_stops_on_first_failed_refresh(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(module, "parse_args", lambda: make_daily_backtest_refresh_args(repo_root=str(tmp_path)))
    monkeypatch.setattr(module, "load_runtime_eligible_account_names", lambda: ["acct1", "acct2"])
    monkeypatch.setattr(module, "already_completed_today", lambda _log_dir, _day_tag: False)
    run_refresh = Mock(
        side_effect=[
            {
                "account": "acct1",
                "status": "failed",
                "attempts": 2,
                "run_id": None,
                "started_at": "2026-04-14T00:00:00+00:00",
                "finished_at": "2026-04-14T00:00:01+00:00",
                "last_exit_code": 1,
                "transient": False,
            }
        ]
    )
    monkeypatch.setattr(module, "run_backtest_refresh_with_retry", run_refresh)

    assert module.main() == 1
    run_refresh.assert_called_once()


def test_main_validates_attempt_and_backoff(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.setattr(
        module, "parse_args", lambda: make_daily_backtest_refresh_args(repo_root=str(tmp_path), max_attempts=0)
    )
    assert module.main() == 1
    assert "max-attempts" in capsys.readouterr().err

    monkeypatch.setattr(
        module, "parse_args", lambda: make_daily_backtest_refresh_args(repo_root=str(tmp_path), backoff_seconds=-1.0)
    )
    assert module.main() == 1
    assert "backoff-seconds" in capsys.readouterr().err
