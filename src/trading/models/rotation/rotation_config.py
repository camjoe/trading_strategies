from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RotationConfig:
    enabled: bool | None = None
    interval_days: int | None = None
    interval_minutes: int | None = None
    lookback_days: int | None = None
    schedule: list[str] | None = None
    active_index: int | None = None
    last_at: str | None = None
    active_strategy: str | None = None

    def to_db_dict(self) -> dict[str, object]:
        """Map fields to account-table column values.

        The list-valued ``rotation_schedule`` column is returned as a raw list; JSON
        encoding is applied by ``trading.domain.rotation.rotation_config_to_db_dict``.
        The dead mode/optimality/regime/overlay columns are left at their DB
        defaults — no longer written from config.
        """
        return {
            "rotation_enabled": self.enabled,
            "rotation_interval_days": self.interval_days,
            "rotation_interval_minutes": self.interval_minutes,
            "rotation_lookback_days": self.lookback_days,
            "rotation_schedule": self.schedule,
            "rotation_active_index": self.active_index,
            "rotation_last_at": self.last_at,
            "rotation_active_strategy": self.active_strategy,
        }
