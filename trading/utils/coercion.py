"""Stable boundary adapter for coercion utilities.

Domain and service code imports coercion helpers from here rather than
depending on the canonical implementation module directly.
"""

from __future__ import annotations

import sqlite3

from common.coercion import (
    coerce_bool as _coerce_bool,
    coerce_float as _coerce_float,
    coerce_int as _coerce_int,
    coerce_str as _coerce_str,
    expect_float as _expect_float,
    expect_int as _expect_int,
    expect_str as _expect_str,
    row_expect_float as _row_expect_float,
    row_expect_int as _row_expect_int,
    row_expect_str as _row_expect_str,
    row_float as _row_float,
    row_int as _row_int,
    row_str as _row_str,
)


def coerce_str(value: object | None) -> str | None:
    return _coerce_str(value)


def coerce_float(value: object | None) -> float | None:
    return _coerce_float(value)


def coerce_int(value: object | None) -> int | None:
    return _coerce_int(value)


def coerce_bool(value: object | None) -> bool | None:
    return _coerce_bool(value)


def expect_str(value: object | None, field_name: str = "value") -> str:
    return _expect_str(value, field_name)


def expect_float(value: object | None, field_name: str = "value") -> float:
    return _expect_float(value, field_name)


def expect_int(value: object | None, field_name: str = "value") -> int:
    return _expect_int(value, field_name)


def row_str(row: sqlite3.Row, key: str) -> str | None:
    return _row_str(row, key)


def row_expect_str(row: sqlite3.Row, key: str) -> str:
    return _row_expect_str(row, key)


def row_float(row: sqlite3.Row, key: str) -> float | None:
    return _row_float(row, key)


def row_expect_float(row: sqlite3.Row, key: str) -> float:
    return _row_expect_float(row, key)


def row_int(row: sqlite3.Row, key: str) -> int | None:
    return _row_int(row, key)


def row_expect_int(row: sqlite3.Row, key: str) -> int:
    return _row_expect_int(row, key)


def to_float_obj(value: object) -> object:
    return _expect_float(value)


def to_int_obj(value: object) -> object:
    return _expect_int(value)
