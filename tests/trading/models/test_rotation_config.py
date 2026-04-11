import pytest

from trading.models.rotation_config import RotationConfig


class TestRotationConfigFromProfile:
    def test_minimal_disabled_profile(self):
        rc = RotationConfig.from_profile({"rotation_enabled": False})
        assert rc.enabled is False
        assert rc.mode == "time"
        assert rc.optimality_mode == "previous_period_best"

    def test_enabled_with_interval_and_schedule(self):
        rc = RotationConfig.from_profile({
            "rotation_enabled": True,
            "rotation_interval_days": 7,
            "rotation_schedule": ["momentum", "meanrev"],
        })
        assert rc.enabled is True
        assert rc.interval_days == 7
        assert rc.schedule == ["momentum", "meanrev"]
        assert rc.active_index == 0
        assert rc.active_strategy == "momentum"

    def test_explicit_active_index_sets_strategy(self):
        rc = RotationConfig.from_profile({
            "rotation_enabled": True,
            "rotation_interval_days": 7,
            "rotation_schedule": ["a", "b", "c"],
            "rotation_active_index": 1,
        })
        assert rc.active_index == 1
        assert rc.active_strategy == "b"

    def test_explicit_active_strategy_sets_index(self):
        rc = RotationConfig.from_profile({
            "rotation_enabled": True,
            "rotation_interval_days": 7,
            "rotation_schedule": ["a", "b", "c"],
            "rotation_active_strategy": "b",
        })
        assert rc.active_index == 1
        assert rc.active_strategy == "b"

    def test_active_index_wraps_when_exceeds_schedule_length(self):
        rc = RotationConfig.from_profile({
            "rotation_enabled": True,
            "rotation_interval_days": 7,
            "rotation_schedule": ["a", "b"],
            "rotation_active_index": 4,  # 4 % 2 = 0
        })
        assert rc.active_index == 0
        assert rc.active_strategy == "a"

    def test_optimal_rotation_mode(self):
        rc = RotationConfig.from_profile({
            "rotation_mode": "optimal",
            "rotation_optimality_mode": "average_return",
        })
        assert rc.mode == "optimal"
        assert rc.optimality_mode == "average_return"

    def test_hybrid_weighted_optimality_mode(self):
        rc = RotationConfig.from_profile({
            "rotation_mode": "optimal",
            "rotation_optimality_mode": "hybrid_weighted",
        })
        assert rc.mode == "optimal"
        assert rc.optimality_mode == "hybrid_weighted"

    def test_lookback_days_and_last_at_stored(self):
        rc = RotationConfig.from_profile({
            "rotation_lookback_days": 30,
            "rotation_last_at": "2026-01-01T00:00:00Z",
        })
        assert rc.lookback_days == 30
        assert rc.last_at == "2026-01-01T00:00:00Z"

    def test_invalid_rotation_mode_raises(self):
        with pytest.raises(ValueError, match="rotation_mode"):
            RotationConfig.from_profile({"rotation_mode": "orbital"})

    def test_invalid_optimality_mode_raises(self):
        with pytest.raises(ValueError, match="rotation_optimality_mode"):
            RotationConfig.from_profile({"rotation_optimality_mode": "random_pick"})

    def test_enabled_without_interval_raises(self):
        with pytest.raises(ValueError, match="rotation_interval_days"):
            RotationConfig.from_profile({"rotation_enabled": True})

    def test_lookback_days_zero_raises(self):
        with pytest.raises(ValueError, match="rotation_lookback_days"):
            RotationConfig.from_profile({"rotation_lookback_days": 0})

    def test_lookback_days_negative_raises(self):
        with pytest.raises(ValueError, match="rotation_lookback_days"):
            RotationConfig.from_profile({"rotation_lookback_days": -5})

    def test_active_index_negative_raises(self):
        with pytest.raises(ValueError, match="rotation_active_index"):
            RotationConfig.from_profile({"rotation_active_index": -1})

    def test_active_strategy_not_in_schedule_raises(self):
        with pytest.raises(ValueError, match="rotation_active_strategy"):
            RotationConfig.from_profile({
                "rotation_enabled": True,
                "rotation_interval_days": 7,
                "rotation_schedule": ["a", "b"],
                "rotation_active_strategy": "z",
            })

    def test_empty_profile_uses_defaults(self):
        rc = RotationConfig.from_profile({})
        assert rc.enabled is None
        assert rc.mode == "time"
        assert rc.optimality_mode == "previous_period_best"
        assert rc.interval_days is None
        assert rc.schedule is None
