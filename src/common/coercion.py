"""Value and row coercion helpers shared across packages.

Two independent axes, giving four families:

* ``coerce_*`` / ``expect_*`` convert a single value; ``row_*`` / ``row_expect_*``
  read one key out of a mapping.
* ``coerce_*`` / ``row_*`` pass ``None`` through; ``expect_*`` / ``row_expect_*``
  raise :class:`ValueError` on ``None``, so a caller that requires a value gets a
  non-optional type back instead of narrowing one itself. Both kinds raise
  ``ValueError`` when a non-null value cannot be converted.

The ``row_*`` families take a :class:`~collections.abc.Mapping`, **not** a
``sqlite3.Row`` — that class is a sequence, not a mapping, and does not satisfy
the signature. Repositories already convert at the boundary (``dict(row)``,
usually straight into a model's ``from_mapping``); these helpers sit on the
mapping side of it.

Prefer ``row_expect_x(row, key)`` over ``expect_x(row[key])``: it passes the
column name through, so a bad value reports ``book_id cannot be null`` rather
than ``value cannot be null``.

No domain dependencies; usable from any layer.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any


def coerce_str(value: object | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def coerce_float(value: object | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float, str)):
        return float(value)
    raise ValueError(f"Expected float-convertible value, got {type(value).__name__}")


def coerce_int(value: object | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float, str)):
        return int(value)
    raise ValueError(f"Expected int-convertible value, got {type(value).__name__}")


def coerce_bool(value: object | None) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    raise ValueError(f"Invalid boolean value: {value}")


def expect_str(value: object | None, field_name: str = "value") -> str:
    converted = coerce_str(value)
    if converted is None:
        raise ValueError(f"{field_name} cannot be null")
    return converted


def expect_float(value: object | None, field_name: str = "value") -> float:
    converted = coerce_float(value)
    if converted is None:
        raise ValueError(f"{field_name} cannot be null")
    return converted


def expect_int(value: object | None, field_name: str = "value") -> int:
    converted = coerce_int(value)
    if converted is None:
        raise ValueError(f"{field_name} cannot be null")
    return converted


def row_str(row: Mapping[str, object], key: str) -> str | None:
    return coerce_str(row[key])


def row_expect_str(row: Mapping[str, object], key: str) -> str:
    return expect_str(row[key], key)


def row_float(row: Mapping[str, object], key: str) -> float | None:
    return coerce_float(row[key])


def row_expect_float(row: Mapping[str, object], key: str) -> float:
    return expect_float(row[key], key)


def row_int(row: Mapping[str, object], key: str) -> int | None:
    return coerce_int(row[key])


def row_expect_int(row: Mapping[str, object], key: str) -> int:
    return expect_int(row[key], key)


def row_json_object(row: Mapping[str, object], key: str) -> dict[str, Any]:
    """Decode a JSON *object* column, rejecting any other shape.

    Returns ``dict[str, Any]`` because a decoded payload's value types are only
    known to its caller; the guard here is the outer shape, which several callers
    would otherwise assume. A NULL column reads as an empty dict.
    """
    raw = row[key]
    if raw is None:
        return {}
    payload = json.loads(str(raw))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object in column '{key}'.")
    return payload
