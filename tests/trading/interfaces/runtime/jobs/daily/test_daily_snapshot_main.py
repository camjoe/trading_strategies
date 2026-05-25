from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path

import pytest
from tests.trading.interfaces.runtime.jobs.loaders import daily_snapshot as module, make_daily_snapshot_args


def test_parse_args_reads_cli_overrides(monkeypatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "snapshot",
            "--accounts",
            "acct1,acct2",
            "--force-run",
            "--run-source",
            "manual",
            "--enable-run",
            "--max-attempts",
            "5",
            "--backoff-seconds",
            "1.5",
        ],
    )

    args = module.parse_args()

    assert args.accounts == "acct1,acct2"
    assert args.force_run is True
    assert args.run_source == "manual"
    assert args.enable_run is True
    assert args.max_attempts == 5
    assert args.backoff_seconds == 1.5


def test_is_run_enabled_true_when_flag_set(monkeypatch) -> None:
    monkeypatch.delenv(module.DAILY_SNAPSHOT_ENABLED_ENV, raising=False)
    assert module.is_run_enabled(make_daily_snapshot_args(enable_run=True)) is True


def test_is_run_enabled_true_when_env_set(monkeypatch) -> None:
    monkeypatch.setenv(module.DAILY_SNAPSHOT_ENABLED_ENV, "true")
    assert module.is_run_enabled(make_daily_snapshot_args(enable_run=False)) is True


def test_is_run_enabled_false_by_default(monkeypatch) -> None:
    monkeypatch.delenv(module.DAILY_SNAPSHOT_ENABLED_ENV, raising=False)
    assert module.is_run_enabled(make_daily_snapshot_args(enable_run=False)) is False


def test_main_rejects_non_positive_max_attempts(monkeypatch, capsys) -> None:
    monkeypatch.setattr(module, "parse_args", lambda: make_daily_snapshot_args(max_attempts=0))

    assert module.main() == 1
    assert "--max-attempts must be >= 1" in capsys.readouterr().err


def test_main_rejects_negative_backoff(monkeypatch, capsys) -> None:
    monkeypatch.setattr(module, "parse_args", lambda: make_daily_snapshot_args(backoff_seconds=-0.5))

    assert module.main() == 1
    assert "--backoff-seconds must be >= 0" in capsys.readouterr().err


def test_main_reports_disabled_runs(monkeypatch, capsys) -> None:
    monkeypatch.setattr(module, "parse_args", lambda: make_daily_snapshot_args(enable_run=False))
    monkeypatch.setattr(module, "is_run_enabled", lambda _args: False)

    assert module.main() == 0
    assert "Daily snapshot run is disabled" in capsys.readouterr().err


def test_main_reports_account_resolution_errors(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(module, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(module, "SNAPSHOTS_EXPORT_DIR", tmp_path / "exports")
    monkeypatch.setattr(module, "parse_args", lambda: make_daily_snapshot_args())
    monkeypatch.setattr(module, "load_runtime_eligible_account_names", lambda: ["acct1"])
    monkeypatch.setattr(module, "resolve_accounts", lambda *_args: (_ for _ in ()).throw(ValueError("bad accounts")))

    assert module.main() == 1
    assert "bad accounts" in capsys.readouterr().err


def test_main_requires_at_least_one_account(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(module, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(module, "SNAPSHOTS_EXPORT_DIR", tmp_path / "exports")
    monkeypatch.setattr(module, "parse_args", lambda: make_daily_snapshot_args())
    monkeypatch.setattr(module, "load_runtime_eligible_account_names", lambda: ["acct1"])
    monkeypatch.setattr(module, "resolve_accounts", lambda *_args: [])

    assert module.main() == 1
    assert "No accounts specified." in capsys.readouterr().err


def test_main_writes_skipped_artifact_for_duplicate_run(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(module, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(module, "SNAPSHOTS_EXPORT_DIR", tmp_path / "exports")
    monkeypatch.setattr(module, "parse_args", lambda: make_daily_snapshot_args(force_run=False))
    monkeypatch.setattr(module, "load_runtime_eligible_account_names", lambda: ["acct1"])
    monkeypatch.setattr(module, "already_completed_today", lambda _log_dir, _day_tag: True)

    assert module.main() == 0

    artifacts = list((tmp_path / "exports").glob("daily_snapshot_*.json"))
    assert len(artifacts) == 1
    payload = json.loads(artifacts[0].read_text(encoding="utf-8"))
    assert payload["status"] == "skipped"
    assert payload["skip_reason"] == "already-completed-today"
    assert payload["results"] == []


def test_main_stops_after_first_failed_account(monkeypatch, tmp_path: Path) -> None:
    calls: list[str] = []
    log_messages: list[str] = []

    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(module, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(module, "SNAPSHOTS_EXPORT_DIR", tmp_path / "exports")
    monkeypatch.setattr(module, "parse_args", lambda: make_daily_snapshot_args())
    monkeypatch.setattr(module, "load_runtime_eligible_account_names", lambda: ["acct1", "acct2"])
    monkeypatch.setattr(module, "already_completed_today", lambda _log_dir, _day_tag: False)
    monkeypatch.setattr(module, "tee_line", lambda _path, message: log_messages.append(message))

    def fake_run_snapshot_with_retry(**kwargs):
        calls.append(kwargs["account"])
        return {
            "account": kwargs["account"],
            "status": "failed",
            "attempts": 2,
            "started_at": "2026-03-27T00:00:00+00:00",
            "finished_at": "2026-03-27T00:00:01+00:00",
            "last_exit_code": 1,
            "transient": True,
        }

    monkeypatch.setattr(module, "run_snapshot_with_retry", fake_run_snapshot_with_retry)

    assert module.main() == 1
    assert calls == ["acct1"]
    assert any("Snapshot failed for account=acct1" in message for message in log_messages)

    artifacts = list((tmp_path / "exports").glob("daily_snapshot_*.json"))
    assert len(artifacts) == 1
    payload = json.loads(artifacts[0].read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    assert len(payload["results"]) == 1


def test_main_uses_module_level_repo_paths(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(module, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(module, "SNAPSHOTS_EXPORT_DIR", tmp_path / "exports")
    monkeypatch.setattr(module, "parse_args", lambda: make_daily_snapshot_args())
    monkeypatch.setattr(module, "load_runtime_eligible_account_names", lambda: ["acct1"])
    monkeypatch.setattr(module, "already_completed_today", lambda _log_dir, _day_tag: False)
    monkeypatch.setattr(
        module,
        "run_snapshot_with_retry",
        lambda **_kwargs: {
            "account": "acct1",
            "status": "success",
            "attempts": 1,
            "started_at": "2026-03-27T00:00:00+00:00",
            "finished_at": "2026-03-27T00:00:01+00:00",
            "last_exit_code": 0,
        },
    )

    assert module.main() == 0

    artifacts = list((tmp_path / "exports").glob("daily_snapshot_*.json"))
    assert len(artifacts) == 1
    payload = json.loads(artifacts[0].read_text(encoding="utf-8"))
    assert Path(payload["log_path"]).parts[0] == "logs"
    assert Path(payload["artifact_path"]).parts[0] == "exports"
    assert payload["results"][0]["status"] == "success"


def test_run_snapshot_with_retry_returns_fallback_when_loop_never_runs(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("builtins.max", lambda _a, _b: 0)

    result = module.run_snapshot_with_retry(
        log_path=tmp_path / "snapshot.log",
        repo_root=tmp_path,
        account="acct1",
        max_attempts=3,
        base_backoff_seconds=1.0,
        run_command_fn=lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("should not run")),
    )

    assert result["status"] == "failed"
    assert result["attempts"] == 0


def test_daily_snapshot_module_main_entrypoint(monkeypatch) -> None:
    monkeypatch.delenv(module.DAILY_SNAPSHOT_ENABLED_ENV, raising=False)
    monkeypatch.setattr(sys, "argv", ["snapshot"])

    with pytest.raises(SystemExit) as excinfo:
        runpy.run_module(module.__name__, run_name="__main__")

    assert excinfo.value.code == 0
