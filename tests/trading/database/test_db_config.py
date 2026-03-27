import json
from pathlib import Path

import pytest

from trading.database import db_config


class TestPathFromFile:
    def test_returns_none_when_config_missing(self, tmp_path: Path) -> None:
        config_path = tmp_path / "missing.json"

        assert db_config._path_from_file(config_path) is None

    def test_returns_none_for_blank_db_path(self, tmp_path: Path) -> None:
        config_path = tmp_path / "db_config.json"
        config_path.write_text(json.dumps({"db_path": "   "}), encoding="utf-8")

        assert db_config._path_from_file(config_path) is None

    def test_resolves_relative_path_from_repo_root(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        config_path = tmp_path / "db_config.json"
        config_path.write_text(json.dumps({"db_path": "local/custom.db"}), encoding="utf-8")
        monkeypatch.setattr(db_config, "_REPO_ROOT", tmp_path)

        resolved = db_config._path_from_file(config_path)

        assert resolved == (tmp_path / "local" / "custom.db").resolve()

    def test_resolves_absolute_path_from_config(self, tmp_path: Path) -> None:
        db_path = (tmp_path / "absolute.db").resolve()
        config_path = tmp_path / "db_config.json"
        config_path.write_text(json.dumps({"db_path": str(db_path)}), encoding="utf-8")

        assert db_config._path_from_file(config_path) == db_path


class TestGetDbPath:
    def test_prefers_env_path_over_config(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        env_db = tmp_path / "env.db"
        config_path = tmp_path / "db_config.json"
        config_path.write_text(json.dumps({"db_path": "from_config.db"}), encoding="utf-8")

        monkeypatch.setenv("TRADING_DB_PATH", str(env_db))
        monkeypatch.setenv("TRADING_DB_CONFIG", str(config_path))

        assert db_config.get_db_path() == env_db.resolve()

    def test_uses_config_file_when_env_not_set(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        config_path = tmp_path / "db_config.json"
        configured_db = tmp_path / "from_config.db"
        config_path.write_text(json.dumps({"db_path": str(configured_db)}), encoding="utf-8")

        monkeypatch.delenv("TRADING_DB_PATH", raising=False)
        monkeypatch.setenv("TRADING_DB_CONFIG", str(config_path))

        assert db_config.get_db_path() == configured_db.resolve()

    def test_falls_back_to_default_db_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("TRADING_DB_PATH", raising=False)
        monkeypatch.delenv("TRADING_DB_CONFIG", raising=False)
        monkeypatch.setattr(db_config, "_DEFAULT_DB_PATH", tmp_path / "fallback.db")
        monkeypatch.setattr(db_config, "_DEFAULT_CONFIG_PATH", tmp_path / "missing_config.json")

        assert db_config.get_db_path() == tmp_path / "fallback.db"

    def test_config_path_uses_env_override(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        custom_config = tmp_path / "custom_config.json"
        monkeypatch.setenv("TRADING_DB_CONFIG", str(custom_config))

        assert db_config._config_path() == custom_config.resolve()
