from __future__ import annotations

from dataclasses import dataclass

from trading.utils.coercion import coerce_bool, coerce_float, coerce_int, coerce_str
from trading.domain.rotation import (
    OPTIMALITY_MODES,
    ROTATION_MODES,
    ROTATION_OVERLAY_MODES,
    dump_rotation_overlay_watchlist,
    parse_rotation_schedule,
    parse_rotation_overlay_watchlist,
)


@dataclass(frozen=True)
class RotationConfig:
    enabled: bool | None = None
    mode: str | None = None
    optimality_mode: str | None = None
    interval_days: int | None = None
    interval_minutes: int | None = None
    lookback_days: int | None = None
    schedule: list[str] | None = None
    regime_strategy_risk_on: str | None = None
    regime_strategy_neutral: str | None = None
    regime_strategy_risk_off: str | None = None
    overlay_mode: str | None = None
    overlay_min_tickers: int | None = None
    overlay_confidence_threshold: float | None = None
    overlay_watchlist: list[str] | None = None
    active_index: int | None = None
    last_at: str | None = None
    active_strategy: str | None = None

    @classmethod
    def from_profile(cls, profile: dict[str, object]) -> RotationConfig:
        def _validate_strategy_field(value: str | None, field_name: str) -> str | None:
            from trading.backtesting.domain.strategy_signals import validate_strategy_name

            if value is None:
                return None
            strategy_name = value.strip()
            if not strategy_name:
                return None
            try:
                validate_strategy_name(strategy_name)
            except ValueError as exc:
                raise ValueError(f"{field_name}: {exc}") from exc
            return strategy_name

        enabled = coerce_bool(profile.get("rotation_enabled"))
        rotation_mode_raw = coerce_str(profile.get("rotation_mode"))
        optimality_mode_raw = coerce_str(profile.get("rotation_optimality_mode"))
        interval_days = coerce_int(profile.get("rotation_interval_days"))
        interval_minutes = coerce_int(profile.get("rotation_interval_minutes"))
        lookback_days = coerce_int(profile.get("rotation_lookback_days"))
        regime_strategy_risk_on = _validate_strategy_field(
            coerce_str(profile.get("rotation_regime_strategy_risk_on")),
            "rotation_regime_strategy_risk_on",
        )
        regime_strategy_neutral = _validate_strategy_field(
            coerce_str(profile.get("rotation_regime_strategy_neutral")),
            "rotation_regime_strategy_neutral",
        )
        regime_strategy_risk_off = _validate_strategy_field(
            coerce_str(profile.get("rotation_regime_strategy_risk_off")),
            "rotation_regime_strategy_risk_off",
        )
        overlay_mode_raw = coerce_str(profile.get("rotation_overlay_mode"))
        overlay_min_tickers = coerce_int(profile.get("rotation_overlay_min_tickers"))
        overlay_confidence_threshold_raw = profile.get("rotation_overlay_confidence_threshold")
        overlay_watchlist = (
            parse_rotation_overlay_watchlist(profile.get("rotation_overlay_watchlist"))
            if "rotation_overlay_watchlist" in profile
            else None
        )
        active_index = coerce_int(profile.get("rotation_active_index"))
        last_at = coerce_str(profile.get("rotation_last_at"))
        active_strategy = _validate_strategy_field(
            coerce_str(profile.get("rotation_active_strategy")),
            "rotation_active_strategy",
        )
        schedule = parse_rotation_schedule(profile.get("rotation_schedule"))
        for index, strategy_name in enumerate(schedule):
            _validate_strategy_field(strategy_name, f"rotation_schedule[{index}]")

        mode = (rotation_mode_raw or "time").strip().lower()
        if mode not in ROTATION_MODES:
            raise ValueError("rotation_mode must be one of: regime, time, optimal")

        optimality_mode = (optimality_mode_raw or "previous_period_best").strip().lower()
        if optimality_mode not in OPTIMALITY_MODES:
            allowed = ", ".join(sorted(OPTIMALITY_MODES))
            raise ValueError(f"rotation_optimality_mode must be one of: {allowed}")

        overlay_mode = (overlay_mode_raw or "none").strip().lower()
        if overlay_mode not in ROTATION_OVERLAY_MODES:
            allowed = ", ".join(sorted(ROTATION_OVERLAY_MODES))
            raise ValueError(f"rotation_overlay_mode must be one of: {allowed}")

        if interval_days is not None and interval_days <= 0:
            raise ValueError("rotation_interval_days must be > 0")
        if interval_minutes is not None and interval_minutes <= 0:
            raise ValueError("rotation_interval_minutes must be > 0")
        if enabled and not (
            (interval_minutes is not None and interval_minutes > 0)
            or (interval_days is not None and interval_days > 0)
        ):
            raise ValueError(
                "rotation interval must be configured with rotation_interval_minutes or rotation_interval_days when rotation_enabled is true"
            )
        if lookback_days is not None and lookback_days <= 0:
            raise ValueError("rotation_lookback_days must be > 0")
        if overlay_min_tickers is not None and overlay_min_tickers <= 0:
            raise ValueError("rotation_overlay_min_tickers must be > 0")
        overlay_confidence_threshold = None
        if overlay_confidence_threshold_raw is not None:
            overlay_confidence_threshold = coerce_float(overlay_confidence_threshold_raw)
            if overlay_confidence_threshold is None:
                raise ValueError("rotation_overlay_confidence_threshold must be numeric")
            if overlay_confidence_threshold <= 0 or overlay_confidence_threshold > 1:
                raise ValueError("rotation_overlay_confidence_threshold must be > 0 and <= 1")
        if active_index is not None and active_index < 0:
            raise ValueError("rotation_active_index must be >= 0")

        if schedule and active_index is not None and active_index >= len(schedule):
            active_index = active_index % len(schedule)

        if schedule and not active_strategy:
            if active_index is None:
                active_index = 0
            active_strategy = schedule[active_index]

        if active_strategy and schedule and active_strategy not in schedule:
            raise ValueError("rotation_active_strategy must be a member of rotation_schedule")

        regime_strategy_map = {
            "risk_on": regime_strategy_risk_on.strip() if regime_strategy_risk_on is not None else None,
            "neutral": regime_strategy_neutral.strip() if regime_strategy_neutral is not None else None,
            "risk_off": regime_strategy_risk_off.strip() if regime_strategy_risk_off is not None else None,
        }
        for regime_state, strategy_name in regime_strategy_map.items():
            if strategy_name and schedule and strategy_name not in schedule:
                raise ValueError(f"rotation_regime_strategy_{regime_state} must be a member of rotation_schedule")

        if enabled and mode == "regime":
            missing_states = [
                regime_state
                for regime_state, strategy_name in regime_strategy_map.items()
                if not strategy_name
            ]
            if missing_states:
                missing = ", ".join(missing_states)
                raise ValueError(
                    f"rotation_regime_strategy_* must be set for regime rotation; missing: {missing}"
                )
        if overlay_mode != "none" and mode != "regime":
            raise ValueError("rotation_overlay_mode requires rotation_mode = regime")

        if schedule and active_strategy and active_index is None:
            active_index = schedule.index(active_strategy)

        return cls(
            enabled=enabled,
            mode=mode,
            optimality_mode=optimality_mode,
            interval_days=interval_days,
            interval_minutes=interval_minutes,
            lookback_days=lookback_days,
            schedule=schedule if schedule else None,
            regime_strategy_risk_on=regime_strategy_map["risk_on"],
            regime_strategy_neutral=regime_strategy_map["neutral"],
            regime_strategy_risk_off=regime_strategy_map["risk_off"],
            overlay_mode=overlay_mode,
            overlay_min_tickers=overlay_min_tickers,
            overlay_confidence_threshold=overlay_confidence_threshold,
            overlay_watchlist=overlay_watchlist,
            active_index=active_index,
            last_at=last_at.strip() if last_at is not None else None,
            active_strategy=active_strategy.strip() if active_strategy is not None else None,
        )

    def to_db_dict(self) -> dict[str, object]:
        from trading.domain.rotation import dump_rotation_schedule
        values: dict[str, object] = {
            "rotation_enabled": self.enabled,
            "rotation_mode": self.mode,
            "rotation_optimality_mode": self.optimality_mode,
            "rotation_interval_days": self.interval_days,
            "rotation_interval_minutes": self.interval_minutes,
            "rotation_lookback_days": self.lookback_days,
            "rotation_schedule": dump_rotation_schedule(self.schedule) if self.schedule else None,
            "rotation_regime_strategy_risk_on": self.regime_strategy_risk_on,
            "rotation_regime_strategy_neutral": self.regime_strategy_neutral,
            "rotation_regime_strategy_risk_off": self.regime_strategy_risk_off,
            "rotation_overlay_mode": self.overlay_mode,
            "rotation_overlay_min_tickers": self.overlay_min_tickers,
            "rotation_overlay_confidence_threshold": self.overlay_confidence_threshold,
            "rotation_active_index": self.active_index,
            "rotation_last_at": self.last_at,
            "rotation_active_strategy": self.active_strategy,
        }
        if self.overlay_watchlist is not None:
            values["rotation_overlay_watchlist"] = dump_rotation_overlay_watchlist(self.overlay_watchlist)
        return values
