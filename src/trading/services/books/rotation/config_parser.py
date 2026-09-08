from __future__ import annotations

import sqlite3
from collections.abc import Mapping

from common.coercion import coerce_bool, coerce_int
from trading.domain.exceptions import ValidationError
from trading.domain.rotation.schedule import parse_rotation_schedule
from trading.domain.strategies.resolution import validate_strategy_name
from trading.models.rotation import BookRotationConfig
from trading.services.accounts.mutations import get_account
from trading.services.books.default_book import default_book_id
from trading.services.books.rotation.engine import write_book_rotation_scheduling


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

    # Translate the present nested-profile keys to the flat scheduling fields the
    # shared writer merges over the persisted row. Absent keys stay absent so the
    # partial-edit (keep-current) semantics carry through.
    updates: dict[str, object] = {}
    if "enabled" in raw:
        updates["rotation_enabled"] = cfg.enabled
    if "lookback_days" in raw:
        updates["rotation_lookback_days"] = cfg.lookback_days
    if "schedule" in raw:
        updates["rotation_schedule"] = cfg.schedule

    account = get_account(conn, name)
    book_id = default_book_id(conn, account_id=account.id)
    write_book_rotation_scheduling(conn, book_id=book_id, updates=updates)
    return True
