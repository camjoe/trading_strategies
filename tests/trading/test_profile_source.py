import json
from pathlib import Path

import pytest

from trading.services.profile_source import JsonAccountProfileSource


class TestJsonAccountProfileSource:
    def test_accepts_path_instance(self, tmp_path: Path) -> None:
        path = tmp_path / "profiles.json"
        path.write_text(json.dumps([{"name": "acct1"}]), encoding="utf-8")

        source = JsonAccountProfileSource(path)
        profiles = source.load_profiles()

        assert profiles == [{"name": "acct1"}]

    def test_dict_without_accounts_defaults_empty(self, tmp_path: Path) -> None:
        path = tmp_path / "profiles.json"
        path.write_text(json.dumps({"meta": {"version": 1}}), encoding="utf-8")

        source = JsonAccountProfileSource(path)

        assert source.load_profiles() == []

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        missing = tmp_path / "does_not_exist.json"
        source = JsonAccountProfileSource(missing)

        with pytest.raises(FileNotFoundError, match="Profile file not found"):
            source.load_profiles()

    def test_non_dict_item_has_indexed_error(self, tmp_path: Path) -> None:
        path = tmp_path / "profiles.json"
        path.write_text(json.dumps([{"name": "ok"}, "not-a-dict"]), encoding="utf-8")

        source = JsonAccountProfileSource(path)

        with pytest.raises(ValueError, match="index 2"):
            source.load_profiles()

    def test_missing_name_has_indexed_error(self, tmp_path: Path) -> None:
        path = tmp_path / "profiles.json"
        path.write_text(json.dumps([{"strategy": "trend"}]), encoding="utf-8")

        source = JsonAccountProfileSource(path)

        with pytest.raises(ValueError, match="index 1"):
            source.load_profiles()
