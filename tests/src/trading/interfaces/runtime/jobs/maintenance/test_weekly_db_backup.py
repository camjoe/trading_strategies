from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest

import trading.interfaces.runtime.jobs.job_helpers as job_helpers
from tests.src.trading.interfaces.helpers import run_module_as_main
from tests.src.trading.interfaces.runtime.jobs.loaders import (
    run_runtime_job_main,
    write_completed_runtime_log,
)
from trading.interfaces.runtime.jobs.job_helpers import week_tag

MODULE_NAME = "trading.interfaces.runtime.jobs.maintenance.weekly_db_backup"


def _load():
    import importlib

    return importlib.import_module(MODULE_NAME)


def _logs_text(tmp_path: Path) -> str:
    return "\n".join(
        p.read_text(encoding="utf-8") for p in (tmp_path / "local" / "logs").glob("weekly_db_backup_*.log")
    )


class TestWeekTag:
    def test_known_date(self) -> None:
        assert week_tag(dt.datetime(2026, 1, 5)) == "2026_W02"

    def test_first_week(self) -> None:
        assert week_tag(dt.datetime(2026, 1, 1)) == "2026_W01"

    def test_week_number_zero_padded(self) -> None:
        _, week_part = week_tag(dt.datetime(2026, 3, 2)).split("_W")
        assert len(week_part) == 2


class TestMain:
    def test_skips_when_backup_already_completed(self, monkeypatch, tmp_path: Path, capsys) -> None:
        module = _load()
        write_completed_runtime_log(
            tmp_path,
            filename_prefix="weekly_db_backup",
            tag=week_tag(dt.datetime.now()),
            sentinel=module.COMPLETE_SENTINEL,
        )

        assert run_runtime_job_main(monkeypatch, tmp_path, MODULE_NAME, []) == 0
        assert "already completed this week" in capsys.readouterr().out

    def test_runs_backup_and_writes_completion_sentinel(self, monkeypatch, tmp_path: Path) -> None:
        module = _load()
        captured: dict[str, object] = {}

        def fake_run_command(log_path, label, cmd, repo_root):
            captured["label"] = label
            captured["cmd"] = cmd
            captured["repo_root"] = repo_root
            return 0, "ok"

        monkeypatch.setattr(module, "run_command", fake_run_command)

        assert (
            run_runtime_job_main(monkeypatch, tmp_path, MODULE_NAME, ["--backup-dir", "custom-backups", "--force-run"])
            == 0
        )
        assert captured["label"] == "Database backup"
        assert captured["cmd"] == ["-m", module.ADMIN_MODULE, "backup-db", "custom-backups"]
        assert module.COMPLETE_SENTINEL in _logs_text(tmp_path)

    def test_returns_nonzero_when_backup_command_fails(self, monkeypatch, tmp_path: Path) -> None:
        module = _load()
        monkeypatch.setattr(module, "run_command", lambda *_args: (5, "failed"))

        assert run_runtime_job_main(monkeypatch, tmp_path, MODULE_NAME, ["--force-run"]) == 5
        assert module.COMPLETE_SENTINEL not in _logs_text(tmp_path)


def test_weekly_db_backup_module_main_entrypoint(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(job_helpers, "run_command", lambda *_args, **_kwargs: (0, "ok"))
    monkeypatch.setattr(sys, "argv", ["weekly_db_backup", "--force-run", "--repo-root", str(tmp_path)])

    with pytest.raises(SystemExit) as excinfo:
        run_module_as_main(MODULE_NAME)

    assert excinfo.value.code == 0
