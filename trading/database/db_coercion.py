"""SQLite coercion helpers — internal trading database layer.

Delegates to ``common.coercion``, which is the canonical source.
Internal trading code may import directly from here or from
``trading.utils.coercion`` (the stable boundary adapter).
"""
from common.coercion import (
    coerce_bool,
    coerce_float,
    coerce_int,
    coerce_str,
    expect_float,
    expect_int,
    expect_str,
    row_expect_float,
    row_expect_int,
    row_expect_str,
    row_float,
    row_int,
    row_str,
)

__all__ = [
    "coerce_bool",
    "coerce_float",
    "coerce_int",
    "coerce_str",
    "expect_float",
    "expect_int",
    "expect_str",
    "row_expect_float",
    "row_expect_int",
    "row_expect_str",
    "row_float",
    "row_int",
    "row_str",
    "to_float_obj",
    "to_int_obj",
]


def to_float_obj(value: object) -> object:
    return expect_float(value)


def to_int_obj(value: object) -> object:
    return expect_int(value)

