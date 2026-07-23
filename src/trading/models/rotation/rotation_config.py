from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BookRotationConfig:
    """Caller-facing book rotation-scheduling input (profiles / admin API).

    Fields mirror the book-owned scheduling columns (ADR 014): the enabled
    gate, the challenger schedule, and the evidence lookback. ``None`` means
    the caller did not supply the field.
    """

    enabled: bool | None = None
    schedule: list[str] | None = None
    lookback_days: int | None = None

    def to_db_dict(self) -> dict[str, object]:
        """Map fields to ``book_rotation_settings`` column values.

        The list-valued ``rotation_schedule`` column is returned as a raw
        list; JSON encoding is applied by the writer via
        ``trading.domain.rotation.schedule.dump_rotation_schedule``.
        """
        return {
            "rotation_enabled": self.enabled,
            "rotation_schedule": self.schedule,
            "rotation_lookback_days": self.lookback_days,
        }
