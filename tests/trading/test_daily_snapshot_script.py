from __future__ import annotations

import importlib.util
import types
from pathlib import Path


def _load_daily_snapshot_module():
    script_path = Path(__file__).resolve().parents[2] / "trading" / "scripts" / "daily_snapshot.py"
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
