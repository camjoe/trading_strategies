"""DB path resolution: the TRADING_DB_PATH override, else the repo default."""

from __future__ import annotations

from pathlib import Path

import pytest

from infrastructure.database import config


def test_env_path_overrides_the_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_db = tmp_path / "env.db"
    monkeypatch.setenv("TRADING_DB_PATH", str(env_db))

    assert config.get_db_path() == env_db.resolve()


def test_env_path_expands_a_user_relative_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRADING_DB_PATH", "~/scratch.db")

    assert config.get_db_path() == (Path.home() / "scratch.db").resolve()


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_env_path_falls_back_to_the_default(blank: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRADING_DB_PATH", blank)
    monkeypatch.setattr(config, "_DEFAULT_DB_PATH", tmp_path / "fallback.db")

    assert config.get_db_path() == tmp_path / "fallback.db"


def test_falls_back_to_the_default_when_env_is_unset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TRADING_DB_PATH", raising=False)
    monkeypatch.setattr(config, "_DEFAULT_DB_PATH", tmp_path / "fallback.db")

    assert config.get_db_path() == tmp_path / "fallback.db"


def test_a_stray_config_file_no_longer_redirects_the_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "db_config.json").write_text('{"db_path": "local/somewhere_else.db"}', encoding="utf-8")
    monkeypatch.delenv("TRADING_DB_PATH", raising=False)
    monkeypatch.setenv("TRADING_DB_CONFIG", str(tmp_path / "db_config.json"))
    monkeypatch.setattr(config, "_DEFAULT_DB_PATH", tmp_path / "fallback.db")

    assert config.get_db_path() == tmp_path / "fallback.db"
