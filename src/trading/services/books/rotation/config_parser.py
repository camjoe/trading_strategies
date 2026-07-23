from __future__ import annotations

from collections.abc import Mapping

from common.coercion import coerce_bool, coerce_int
from trading.domain.exceptions import ValidationError
from trading.domain.strategies.resolution import validate_strategy_name
from trading.domain.rotation import parse_rotation_schedule
from trading.models.rotation.rotation_config import BookRotationConfig


def _validated_strategy_name(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    strategy_name = value.strip()
    if not strategy_name:
        return None
    try:
        validate_strategy_name(strategy_name)
    except ValueError as exc:
        raise ValidationError(f"{field_name}: {exc}") from exc
    return strategy_name


def parse_book_rotation_config_from_profile(profile: Mapping[str, object]) -> BookRotationConfig:
    """Parse the profile's nested ``rotation`` object (book-owned, ADR 014).

    Shape: ``{"rotation": {"enabled": bool, "schedule": [names], "lookback_days": int}}``.
    Absent keys stay ``None`` so the writer can merge over the persisted row.
    """
    raw = profile.get("rotation")
    if raw is None:
        return BookRotationConfig()
    if not isinstance(raw, Mapping):
        raise ValidationError("rotation must be an object with enabled/schedule/lookback_days")

    enabled = coerce_bool(raw.get("enabled"))
    lookback_days = coerce_int(raw.get("lookback_days"))
    schedule = parse_rotation_schedule(raw.get("schedule"))
    for index, strategy_name in enumerate(schedule):
        _validated_strategy_name(strategy_name, f"rotation.schedule[{index}]")

    if lookback_days is not None and lookback_days <= 0:
        raise ValidationError("rotation.lookback_days must be > 0")

    return BookRotationConfig(
        enabled=enabled,
        schedule=schedule if schedule else None,
        lookback_days=lookback_days,
    )
