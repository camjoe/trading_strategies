from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING

from common.time import parse_utc_iso

if TYPE_CHECKING:
    pass


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


def parse_rotation_schedule(raw_value: object | None) -> list[str]:
    return _parse_unique_string_list(
        raw_value,
        field_name="rotation_schedule",
        item_label="strategy ids",
    )


def dump_rotation_schedule(schedule: list[str]) -> str:
    return json.dumps(schedule, separators=(",", ":"))
