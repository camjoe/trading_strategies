"""Runtime settings models for runtime-settings consumers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeThrottleSettings:
    max_trades_per_day: int | None = None
    max_trades_per_minute: int | None = None


__all__ = [
    "RuntimeThrottleSettings",
]
