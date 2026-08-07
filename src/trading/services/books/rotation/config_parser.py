from __future__ import annotations

import sqlite3
from collections.abc import Mapping

from common.coercion import coerce_bool, coerce_int
from common.time import utc_now_iso
from trading.domain.exceptions import ValidationError
from trading.domain.rotation.schedule import dump_rotation_schedule, parse_rotation_schedule
from trading.domain.strategies.resolution import validate_strategy_name
from trading.models.rotation import BookRotationConfig
from trading.repositories.book_bridge import default_book_id
from trading.repositories.book_settings import BookRotationSettingsRepository
from trading.services.accounts import get_account


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


def apply_book_rotation_settings(conn: sqlite3.Connection, name: str, settings: dict[str, object]) -> bool:
    """Apply *settings*' nested ``rotation`` object to an account's default book.

    Rotation scheduling is book-owned (ADR 014). Keys absent from the
    ``rotation`` object keep their persisted values (partial edit). Returns
    whether anything was written.
    """
    raw = settings.get("rotation")
    if raw is None:
        return False
    cfg = parse_book_rotation_config_from_profile(settings)
    assert isinstance(raw, Mapping)  # parse rejects non-mapping values

    account = get_account(conn, name)
    book_id = default_book_id(conn, account.id)
    repository = BookRotationSettingsRepository(conn)
    current = repository.fetch(book_id=book_id)

    if "enabled" in raw:
        enabled = int(bool(cfg.enabled))
    else:
        enabled = int(current.rotation_enabled) if current is not None else 0
    if "lookback_days" in raw:
        lookback_days = cfg.lookback_days
    else:
        lookback_days = current.rotation_lookback_days if current is not None else None
    if "schedule" in raw:
        schedule = dump_rotation_schedule(cfg.schedule) if cfg.schedule else None
    else:
        schedule = current.rotation_schedule if current is not None else None

    now_iso = utc_now_iso()
    repository.upsert_rotation_scheduling(
        book_id=book_id,
        rotation_enabled=enabled,
        rotation_lookback_days=lookback_days,
        rotation_schedule=schedule,
        created_at=current.created_at if current is not None else now_iso,
        updated_at=now_iso,
    )
    return True
