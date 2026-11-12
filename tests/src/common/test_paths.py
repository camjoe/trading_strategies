from __future__ import annotations

from pathlib import Path

import pytest

from common.paths import LOCAL_DIR, data_home, db_backups_dir, env_path, relative_posix


def test_relative_posix_uses_forward_slashes(tmp_path) -> None:
    path = tmp_path / "a" / "b" / "file.txt"
    path.parent.mkdir(parents=True)
    path.write_text("x", encoding="utf-8")

    assert relative_posix(path, tmp_path) == "a/b/file.txt"


def test_env_path_is_none_when_unset_or_blank(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SOME_PATH", raising=False)
    assert env_path("SOME_PATH") is None
    monkeypatch.setenv("SOME_PATH", "   ")
    assert env_path("SOME_PATH") is None


def test_env_path_is_absolute(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SOME_PATH", "relative/dir")

    assert env_path("SOME_PATH") == (tmp_path / "relative" / "dir").resolve()


def test_shared_data_defaults_to_this_checkout() -> None:
    assert data_home() == LOCAL_DIR
    assert db_backups_dir() == LOCAL_DIR / "db_backups"


def test_data_home_moves_the_backup_folder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TRADING_DATA_HOME", str(tmp_path / "shared"))

    assert data_home() == (tmp_path / "shared").resolve()
    assert db_backups_dir() == (tmp_path / "shared" / "db_backups").resolve()


def test_backup_folder_setting_wins_over_data_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TRADING_DATA_HOME", str(tmp_path / "shared"))
    monkeypatch.setenv("TRADING_DB_BACKUPS_DIR", str(tmp_path / "backups"))

    assert db_backups_dir() == (tmp_path / "backups").resolve()
