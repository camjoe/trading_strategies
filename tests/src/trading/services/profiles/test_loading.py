import json

import pytest

from trading.services.profiles import load_account_profiles


class TestLoadAccountProfiles:
    def test_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_account_profiles(str(tmp_path / "missing.json"))

    def test_list_format(self, tmp_path):
        f = tmp_path / "profiles.json"
        f.write_text(json.dumps([{"name": "acct1"}, {"name": "acct2"}]))
        profiles = load_account_profiles(str(f))
        assert [p["name"] for p in profiles] == ["acct1", "acct2"]

    def test_dict_format(self, tmp_path):
        f = tmp_path / "profiles.json"
        f.write_text(json.dumps({"accounts": [{"name": "acct1"}]}))
        profiles = load_account_profiles(str(f))
        assert len(profiles) == 1
        assert profiles[0]["name"] == "acct1"

    def test_non_list_raises(self, tmp_path):
        f = tmp_path / "profiles.json"
        f.write_text(json.dumps({"accounts": "not-a-list"}))
        with pytest.raises(ValueError, match="list"):
            load_account_profiles(str(f))

    def test_non_dict_item_raises(self, tmp_path):
        f = tmp_path / "profiles.json"
        f.write_text(json.dumps([{"name": "ok"}, "bad"]))
        with pytest.raises(ValueError, match="not an object"):
            load_account_profiles(str(f))

    def test_missing_name_raises(self, tmp_path):
        f = tmp_path / "profiles.json"
        f.write_text(json.dumps([{"strategy": "x"}]))
        with pytest.raises(ValueError, match="name"):
            load_account_profiles(str(f))

    def test_empty_name_raises(self, tmp_path):
        f = tmp_path / "profiles.json"
        f.write_text(json.dumps([{"name": "   "}]))
        with pytest.raises(ValueError, match="name"):
            load_account_profiles(str(f))
