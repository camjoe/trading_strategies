"""Trading-layer coercion helpers.

This module provides a stable boundary for trading/domain code so callsites do
not depend directly on database implementation modules.
"""

from __future__ import annotations

import sqlite3

from trading.database.db_coercion import (
    coerce_bool as _coerce_bool,
    coerce_float as _coerce_float,
    coerce_int as _coerce_int,
    coerce_str as _coerce_str,
    row_expect_float as _row_expect_float,
    row_expect_int as _row_expect_int,
    row_expect_str as _row_expect_str,
    row_float as _row_float,
    row_int as _row_int,
    row_str as _row_str,
    to_float_obj as _to_float_obj,
    to_int_obj as _to_int_obj,
)


def coerce_str(value: object | None) -> str | None:
    return _coerce_str(value)


def coerce_float(value: object | None) -> float | None:
    return _coerce_float(value)


def coerce_int(value: object | None) -> int | None:
    return _coerce_int(value)


def coerce_bool(value: object | None) -> bool | None:
    return _coerce_bool(value)


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
    return _to_float_obj(value)


def to_int_obj(value: object) -> object:
    return _to_int_obj(value)
