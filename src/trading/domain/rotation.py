from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING, Callable, Mapping

from common.coercion import coerce_int
from common.time import parse_utc_iso

if TYPE_CHECKING:
    from trading.models.rotation.rotation_config import RotationConfig


def _account_field(account: Mapping[str, object], key: str) -> object | None:
    """Safely read an account field from either dict-like rows or mappings."""
    if hasattr(account, "get"):
        return account.get(key)
    try:
        return account[key]
    except KeyError, TypeError:
        return None


def _account_text(account: Mapping[str, object], key: str) -> str:
    return str(_account_field(account, key) or "").strip()


def _coerce_default_int(value: object | None, default: int = 0) -> int:
    converted = coerce_int(value)
    return default if converted is None else converted


def _parse_iso(value: str | None) -> datetime | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return parse_utc_iso(text)
    except ValueError:
        return None


def _parse_unique_string_list(
    raw_value: object | None,
    *,
    field_name: str,
    item_label: str,
    normalizer: Callable[[str], str] | None = None,
) -> list[str]:
    if raw_value is None:
        return []

    if isinstance(raw_value, list):
        raw_items = raw_value
    elif isinstance(raw_value, str):
        text = raw_value.strip()
        if not text:
            return []
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{field_name} must be valid JSON.") from exc
        if not isinstance(decoded, list):
            raise ValueError(f"{field_name} must decode to a list of {item_label}.")
        raw_items = decoded
    else:
        raise ValueError(f"{field_name} must be a list or JSON string.")

    items: list[str] = []
    for item in raw_items:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field_name} items must be non-empty strings.")
        value = item.strip()
        if normalizer is not None:
            value = normalizer(value)
        if value and value not in items:
            items.append(value)

    return items


def _rotation_schedule(account: Mapping[str, object]) -> list[str]:
    return parse_rotation_schedule(_account_field(account, "rotation_schedule"))


def parse_rotation_schedule(raw_value: object | None) -> list[str]:
    return _parse_unique_string_list(
        raw_value,
        field_name="rotation_schedule",
        item_label="strategy ids",
    )


def dump_rotation_schedule(schedule: list[str]) -> str:
    return json.dumps(schedule, separators=(",", ":"))


def rotation_config_to_db_dict(cfg: RotationConfig) -> dict[str, object]:
    """Finalize ``RotationConfig.to_db_dict()`` for persistence.

    The model owns the field→column mapping; this applies the domain-owned JSON
    encoding to the list-valued ``rotation_schedule`` column.
    """
    values = cfg.to_db_dict()
    values["rotation_schedule"] = dump_rotation_schedule(cfg.schedule) if cfg.schedule else None
    return values


def resolve_active_strategy(account: Mapping[str, object]) -> str:
    fallback = _account_text(account, "strategy")
    schedule = _rotation_schedule(account)
    if not schedule:
        active = _account_text(account, "rotation_active_strategy")
        return active or fallback

    active = _account_text(account, "rotation_active_strategy")
    if active and active in schedule:
        return active

    idx = _coerce_default_int(_account_field(account, "rotation_active_index"), default=0)
    return schedule[idx % len(schedule)]
