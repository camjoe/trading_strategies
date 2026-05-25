from __future__ import annotations

import json
from pathlib import Path

from tests.trading.interfaces.runtime.jobs.loaders import daily_snapshot as module, make_daily_snapshot_args


def test_is_run_enabled_true_when_flag_set(monkeypatch) -> None:
    monkeypatch.delenv(module.DAILY_SNAPSHOT_ENABLED_ENV, raising=False)
    assert module.is_run_enabled(make_daily_snapshot_args(enable_run=True)) is True


def test_is_run_enabled_true_when_env_set(monkeypatch) -> None:
    monkeypatch.setenv(module.DAILY_SNAPSHOT_ENABLED_ENV, "true")
    assert module.is_run_enabled(make_daily_snapshot_args(enable_run=False)) is True


def test_is_run_enabled_false_by_default(monkeypatch) -> None:
    monkeypatch.delenv(module.DAILY_SNAPSHOT_ENABLED_ENV, raising=False)
    assert module.is_run_enabled(make_daily_snapshot_args(enable_run=False)) is False


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
