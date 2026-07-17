import pytest

from trading.services.profiles.rotation_config_parser import parse_book_rotation_config_from_profile


class TestParseBookRotationConfigFromProfile:
    def test_minimal_disabled_profile(self):
        rc = parse_book_rotation_config_from_profile({"rotation": {"enabled": False}})
        assert rc.enabled is False
        assert rc.schedule is None
        assert rc.lookback_days is None

    def test_enabled_with_schedule_and_lookback(self):
        rc = parse_book_rotation_config_from_profile(
            {
                "rotation": {
                    "enabled": True,
                    "schedule": ["momentum", "meanrev"],
                    "lookback_days": 90,
                }
            }
        )
        assert rc.enabled is True
        assert rc.schedule == ["momentum", "meanrev"]
        assert rc.lookback_days == 90

    def test_missing_rotation_object_uses_defaults(self):
        rc = parse_book_rotation_config_from_profile({})
        assert rc.enabled is None
        assert rc.schedule is None
        assert rc.lookback_days is None

    def test_non_mapping_rotation_raises(self):
        with pytest.raises(ValueError, match="rotation must be an object"):
            parse_book_rotation_config_from_profile({"rotation": "yes"})

    def test_lookback_days_zero_raises(self):
        with pytest.raises(ValueError, match="rotation.lookback_days"):
            parse_book_rotation_config_from_profile({"rotation": {"lookback_days": 0}})

    def test_lookback_days_negative_raises(self):
        with pytest.raises(ValueError, match="rotation.lookback_days"):
            parse_book_rotation_config_from_profile({"rotation": {"lookback_days": -5}})

    def test_unknown_schedule_strategy_raises(self):
        with pytest.raises(ValueError, match=r"rotation.schedule\[1\]"):
            parse_book_rotation_config_from_profile({"rotation": {"schedule": ["trend", "mystery_strategy"]}})

    def test_blank_schedule_entry_raises(self):
        with pytest.raises(ValueError):
            parse_book_rotation_config_from_profile({"rotation": {"schedule": ["trend", ""]}})
