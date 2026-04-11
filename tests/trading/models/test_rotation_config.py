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

    def test_enabled_with_minute_interval_and_schedule(self):
        rc = RotationConfig.from_profile({
            "rotation_enabled": True,
            "rotation_interval_minutes": 240,
            "rotation_schedule": ["momentum", "meanrev"],
        })
        assert rc.enabled is True
        assert rc.interval_minutes == 240
        assert rc.schedule == ["momentum", "meanrev"]

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

    def test_regime_rotation_mode_requires_strategy_map(self):
        rc = RotationConfig.from_profile({
            "rotation_enabled": True,
            "rotation_mode": "regime",
            "rotation_interval_minutes": 240,
            "rotation_schedule": ["trend", "ma_crossover", "mean_reversion"],
            "rotation_regime_strategy_risk_on": "trend",
            "rotation_regime_strategy_neutral": "ma_crossover",
            "rotation_regime_strategy_risk_off": "mean_reversion",
        })
        assert rc.mode == "regime"
        assert rc.regime_strategy_risk_on == "trend"
        assert rc.regime_strategy_neutral == "ma_crossover"
        assert rc.regime_strategy_risk_off == "mean_reversion"

    def test_regime_rotation_accepts_overlay_settings(self):
        rc = RotationConfig.from_profile({
            "rotation_enabled": True,
            "rotation_mode": "regime",
            "rotation_interval_minutes": 240,
            "rotation_schedule": ["trend", "ma_crossover", "mean_reversion"],
            "rotation_regime_strategy_risk_on": "trend",
            "rotation_regime_strategy_neutral": "ma_crossover",
            "rotation_regime_strategy_risk_off": "mean_reversion",
            "rotation_overlay_mode": "news_social",
            "rotation_overlay_min_tickers": 3,
            "rotation_overlay_confidence_threshold": 0.6,
        })
        assert rc.overlay_mode == "news_social"
        assert rc.overlay_min_tickers == 3
        assert rc.overlay_confidence_threshold == pytest.approx(0.6)

    def test_lookback_days_and_last_at_stored(self):
        rc = RotationConfig.from_profile({
            "rotation_interval_minutes": 60,
            "rotation_lookback_days": 30,
            "rotation_last_at": "2026-01-01T00:00:00Z",
        })
        assert rc.interval_minutes == 60
        assert rc.lookback_days == 30
        assert rc.last_at == "2026-01-01T00:00:00Z"

    def test_invalid_rotation_mode_raises(self):
        with pytest.raises(ValueError, match="rotation_mode"):
            RotationConfig.from_profile({"rotation_mode": "orbital"})

    def test_invalid_optimality_mode_raises(self):
        with pytest.raises(ValueError, match="rotation_optimality_mode"):
            RotationConfig.from_profile({"rotation_optimality_mode": "random_pick"})

    def test_enabled_without_interval_raises(self):
        with pytest.raises(ValueError, match="rotation interval must be configured"):
            RotationConfig.from_profile({"rotation_enabled": True})

    def test_interval_minutes_zero_raises(self):
        with pytest.raises(ValueError, match="rotation_interval_minutes"):
            RotationConfig.from_profile({"rotation_interval_minutes": 0})

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

    def test_regime_strategy_not_in_schedule_raises(self):
        with pytest.raises(ValueError, match="rotation_regime_strategy_risk_off"):
            RotationConfig.from_profile({
                "rotation_enabled": True,
                "rotation_mode": "regime",
                "rotation_interval_days": 7,
                "rotation_schedule": ["trend", "ma_crossover"],
                "rotation_regime_strategy_risk_on": "trend",
                "rotation_regime_strategy_neutral": "ma_crossover",
                "rotation_regime_strategy_risk_off": "mean_reversion",
            })

    def test_regime_rotation_missing_mapping_raises(self):
        with pytest.raises(ValueError, match="rotation_regime_strategy_\\* must be set"):
            RotationConfig.from_profile({
                "rotation_enabled": True,
                "rotation_mode": "regime",
                "rotation_interval_days": 7,
                "rotation_schedule": ["trend", "ma_crossover", "mean_reversion"],
                "rotation_regime_strategy_risk_on": "trend",
                "rotation_regime_strategy_neutral": "ma_crossover",
            })

    def test_overlay_mode_requires_regime_rotation(self):
        with pytest.raises(ValueError, match="rotation_overlay_mode requires rotation_mode = regime"):
            RotationConfig.from_profile({
                "rotation_mode": "time",
                "rotation_overlay_mode": "news",
            })

    def test_empty_profile_uses_defaults(self):
        rc = RotationConfig.from_profile({})
        assert rc.enabled is None
        assert rc.mode == "time"
        assert rc.optimality_mode == "previous_period_best"
        assert rc.interval_days is None
        assert rc.schedule is None
