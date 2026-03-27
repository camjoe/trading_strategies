from __future__ import annotations

import importlib.util
import json
import types
from pathlib import Path


def _load_daily_snapshot_module():
    script_path = Path(__file__).resolve().parents[3] / "trading" / "scripts" / "daily_snapshot.py"
    spec = importlib.util.spec_from_file_location("daily_snapshot_script", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_already_completed_today_detects_sentinel(tmp_path: Path):
    module = _load_daily_snapshot_module()
    day_tag = "20260325"
    log = tmp_path / f"daily_snapshot_{day_tag}_010101.log"
    log.write_text(f"anything\n{module.COMPLETE_SENTINEL}\n", encoding="utf-8")

    assert module.already_completed_today(tmp_path, day_tag) is True


def test_retry_delay_seconds_doubles_each_attempt():
    module = _load_daily_snapshot_module()

    assert module.retry_delay_seconds(2.0, 1) == 2.0
    assert module.retry_delay_seconds(2.0, 2) == 4.0
    assert module.retry_delay_seconds(2.0, 3) == 8.0


def test_run_snapshot_with_retry_retries_transient_then_succeeds(tmp_path: Path):
    module = _load_daily_snapshot_module()
    calls: list[tuple[str, list[str]]] = []
    sleeps: list[float] = []

    responses = [
        (1, "temporary failure while fetching prices; try again"),
        (0, "snapshot saved"),
    ]

    def fake_run_command(log_path, label, args, cwd):
        calls.append((label, args))
        return responses.pop(0)

    result = module.run_snapshot_with_retry(
        log_path=tmp_path / "run.log",
        repo_root=tmp_path,
        account="acct1",
        max_attempts=3,
        base_backoff_seconds=1.5,
        run_command_fn=fake_run_command,
        sleep_fn=sleeps.append,
    )

    assert result["status"] == "success"
    assert result["attempts"] == 2
    assert len(calls) == 2
    assert sleeps == [1.5]


def test_run_snapshot_with_retry_stops_on_non_transient(tmp_path: Path):
    module = _load_daily_snapshot_module()

    def fake_run_command(_log_path, _label, _args, _cwd):
        return 1, "unknown account"

    result = module.run_snapshot_with_retry(
        log_path=tmp_path / "run.log",
        repo_root=tmp_path,
        account="acct1",
        max_attempts=5,
        base_backoff_seconds=1.0,
        run_command_fn=fake_run_command,
        sleep_fn=lambda _seconds: None,
    )

    assert result["status"] == "failed"
    assert result["attempts"] == 1
    assert result["transient"] is False


def test_is_run_enabled_true_when_flag_set(monkeypatch):
    module = _load_daily_snapshot_module()
    monkeypatch.delenv("DAILY_SNAPSHOT_ENABLED", raising=False)

    args = types.SimpleNamespace(enable_run=True)
    assert module.is_run_enabled(args) is True


def test_is_run_enabled_true_when_env_set(monkeypatch):
    module = _load_daily_snapshot_module()
    monkeypatch.setenv("DAILY_SNAPSHOT_ENABLED", "true")

    args = types.SimpleNamespace(enable_run=False)
    assert module.is_run_enabled(args) is True


def test_is_run_enabled_false_by_default(monkeypatch):
    module = _load_daily_snapshot_module()
    monkeypatch.delenv("DAILY_SNAPSHOT_ENABLED", raising=False)

    args = types.SimpleNamespace(enable_run=False)
    assert module.is_run_enabled(args) is False


def test_main_uses_module_level_repo_paths(monkeypatch, tmp_path: Path):
    module = _load_daily_snapshot_module()
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(module, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(module, "SNAPSHOTS_EXPORT_DIR", tmp_path / "exports")
    monkeypatch.setattr(
        module,
        "parse_args",
        lambda: types.SimpleNamespace(
            accounts="all",
            force_run=False,
            run_source="test-run",
            enable_run=True,
            max_attempts=2,
            backoff_seconds=0.0,
        ),
    )
    monkeypatch.setattr(module, "load_all_account_names", lambda: ["acct1"])
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
