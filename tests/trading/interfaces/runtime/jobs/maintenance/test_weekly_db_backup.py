from __future__ import annotations

import datetime as dt
import importlib
import runpy
import sys
from argparse import Namespace
from pathlib import Path

import pytest


def _load():
    return importlib.import_module("trading.interfaces.runtime.jobs.maintenance.weekly_db_backup")


class FixedDateTime(dt.datetime):
    @classmethod
    def now(cls, tz=None) -> "FixedDateTime":
        value = cls(2026, 3, 27, 8, 9, 10)
        if tz is not None:
            return value.replace(tzinfo=tz)
        return value


class TestParseArgs:
    def test_parse_args_defaults(self, monkeypatch) -> None:
        module = _load()
        monkeypatch.setattr(sys, "argv", ["weekly_db_backup"])

        args = module.parse_args()

        assert args.backup_dir == ""
        assert args.force_run is False

    def test_parse_args_reads_flags(self, monkeypatch) -> None:
        module = _load()
        monkeypatch.setattr(sys, "argv", ["weekly_db_backup", "--backup-dir", "backups", "--force-run"])

        args = module.parse_args()

        assert args.backup_dir == "backups"
        assert args.force_run is True


class TestWeekTag:
    def test_known_date(self) -> None:
        result = _load().week_tag(dt.datetime(2026, 1, 5))
        assert result == "2026_W02"

    def test_first_week(self) -> None:
        result = _load().week_tag(dt.datetime(2026, 1, 1))
        assert result == "2026_W01"

    def test_week_number_zero_padded(self) -> None:
        tag = _load().week_tag(dt.datetime(2026, 3, 2))
        assert "_W" in tag
        _, week_part = tag.split("_W")
        assert len(week_part) == 2


class TestAlreadyCompletedThisWeek:
    def test_returns_false_when_no_logs(self, tmp_path: Path) -> None:
        module = _load()
        assert module.already_completed_this_week(tmp_path, "2026_W01") is False

    def test_returns_true_when_sentinel_present(self, tmp_path: Path) -> None:
        module = _load()
        tag = "2026_W99"
        log = tmp_path / f"weekly_db_backup_{tag}_20260101_000000.log"
        log.write_text(f"stuff\n{module.COMPLETE_SENTINEL}\n", encoding="utf-8")
        assert module.already_completed_this_week(tmp_path, tag) is True

    def test_returns_false_when_sentinel_absent(self, tmp_path: Path) -> None:
        module = _load()
        tag = "2026_W88"
        log = tmp_path / f"weekly_db_backup_{tag}_20260101_000000.log"
        log.write_text("incomplete run\n", encoding="utf-8")
        assert module.already_completed_this_week(tmp_path, tag) is False


class TestMain:
    def test_main_skips_when_backup_already_completed(self, monkeypatch, tmp_path: Path, capsys) -> None:
        module = _load()
        monkeypatch.setattr(module, "LOGS_DIR", tmp_path / "logs")
        monkeypatch.setattr(module, "parse_args", lambda: Namespace(backup_dir="", force_run=False))
        monkeypatch.setattr(module, "already_completed_this_week", lambda *_args: True)

        assert module.main() == 0
        assert "already completed this week" in capsys.readouterr().out

    def test_main_runs_backup_and_writes_completion_sentinel(self, monkeypatch, tmp_path: Path) -> None:
        module = _load()
        tee_messages: list[tuple[Path, str]] = []
        captured: dict[str, object] = {}

        monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(module, "LOGS_DIR", tmp_path / "logs")
        monkeypatch.setattr(module.dt, "datetime", FixedDateTime)
        monkeypatch.setattr(module, "parse_args", lambda: Namespace(backup_dir="custom-backups", force_run=False))
        monkeypatch.setattr(module, "already_completed_this_week", lambda *_args: False)
        monkeypatch.setattr(module, "tee_line", lambda path, message: tee_messages.append((path, message)))

        def fake_run_command(log_path: Path, label: str, cmd: list[str], repo_root: Path):
            captured["log_path"] = log_path
            captured["label"] = label
            captured["cmd"] = cmd
            captured["repo_root"] = repo_root
            return 0, "ok"

        monkeypatch.setattr(module, "run_command", fake_run_command)

        assert module.main() == 0
        assert (tmp_path / "logs").exists()
        assert captured["label"] == "Database backup"
        assert captured["cmd"] == ["-m", module.ADMIN_MODULE, "backup-db", "custom-backups"]
        assert captured["repo_root"] == tmp_path
        assert tee_messages[-1][1].endswith(module.COMPLETE_SENTINEL)

    def test_main_returns_nonzero_when_backup_command_fails(self, monkeypatch, tmp_path: Path) -> None:
        module = _load()
        tee_messages: list[str] = []

        monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(module, "LOGS_DIR", tmp_path / "logs")
        monkeypatch.setattr(module.dt, "datetime", FixedDateTime)
        monkeypatch.setattr(module, "parse_args", lambda: Namespace(backup_dir="", force_run=True))
        monkeypatch.setattr(module, "tee_line", lambda _path, message: tee_messages.append(message))
        monkeypatch.setattr(module, "run_command", lambda *_args: (5, "failed"))

        assert module.main() == 5
        assert len(tee_messages) == 1
        assert "RUN META" in tee_messages[0]


def test_weekly_db_backup_module_main_entrypoint(monkeypatch, tmp_path: Path) -> None:
    import common.paths.repo_paths as repo_paths_module
    import trading.interfaces.runtime.jobs.job_helpers as helpers_module

    module = _load()
    monkeypatch.setattr(repo_paths_module, "get_repo_root", lambda _file: tmp_path)
    monkeypatch.setattr(helpers_module, "run_command", lambda *_args, **_kwargs: (0, "ok"))
    monkeypatch.setattr(sys, "argv", ["weekly_db_backup", "--force-run"])

    with pytest.raises(SystemExit) as excinfo:
        runpy.run_module(module.__name__, run_name="__main__")

    assert excinfo.value.code == 0
