from __future__ import annotations

from dataclasses import dataclass

from trading.domain.rotation import (
    dump_rotation_overlay_watchlist,
    dump_rotation_schedule,
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

    def to_db_dict(self) -> dict[str, object]:
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
