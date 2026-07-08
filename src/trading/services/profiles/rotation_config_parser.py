from __future__ import annotations

from collections.abc import Mapping

from common.coercion import coerce_bool, coerce_int, coerce_str
from trading.domain.strategy_signals import validate_strategy_name
from trading.domain.rotation import parse_rotation_schedule
from trading.models.rotation.rotation_config import RotationConfig


def _validated_strategy_name(value: str | None, field_name: str) -> str | None:
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


def parse_rotation_config_from_profile(profile: Mapping[str, object]) -> RotationConfig:
    enabled = coerce_bool(profile.get("rotation_enabled"))
    interval_days = coerce_int(profile.get("rotation_interval_days"))
    interval_minutes = coerce_int(profile.get("rotation_interval_minutes"))
    lookback_days = coerce_int(profile.get("rotation_lookback_days"))
    active_index = coerce_int(profile.get("rotation_active_index"))
    last_at = coerce_str(profile.get("rotation_last_at"))
    active_strategy = _validated_strategy_name(
        coerce_str(profile.get("rotation_active_strategy")),
        "rotation_active_strategy",
    )
    schedule = parse_rotation_schedule(profile.get("rotation_schedule"))
    for index, strategy_name in enumerate(schedule):
        _validated_strategy_name(strategy_name, f"rotation_schedule[{index}]")

    if interval_days is not None and interval_days <= 0:
        raise ValueError("rotation_interval_days must be > 0")
    if interval_minutes is not None and interval_minutes <= 0:
        raise ValueError("rotation_interval_minutes must be > 0")
    if enabled and not (
        (interval_minutes is not None and interval_minutes > 0) or (interval_days is not None and interval_days > 0)
    ):
        raise ValueError(
            "rotation interval must be configured with rotation_interval_minutes"
            " or rotation_interval_days when rotation_enabled is true"
        )
    if lookback_days is not None and lookback_days <= 0:
        raise ValueError("rotation_lookback_days must be > 0")
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

    if schedule and active_strategy and active_index is None:
        active_index = schedule.index(active_strategy)

    return RotationConfig(
        enabled=enabled,
        interval_days=interval_days,
        interval_minutes=interval_minutes,
        lookback_days=lookback_days,
        schedule=schedule if schedule else None,
        active_index=active_index,
        last_at=last_at.strip() if last_at is not None else None,
        active_strategy=active_strategy.strip() if active_strategy is not None else None,
    )
