"""Encode and decode money and quantity columns at the repository boundary.

The repository layer crosses here on every read and write. A money or quantity
column stores an integer at a fixed scale; the domain holds a ``decimal.Decimal``.
These functions bind the pure ``common.money`` conversion to the two fixed scales,
so no repository hand-converts a value.

The persistence package imports nothing from ``trading`` or ``infrastructure``;
``common`` is below both, so it is allowed.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal

from common.coercion import coerce_int
from common.constants import MONEY_MINOR_UNITS_PER_DOLLAR, QUANTITY_MINOR_UNITS_PER_SHARE
from common.money import from_minor_units, to_minor_units


def _as_decimal(value: Decimal | float) -> Decimal:
    # str() first so a float's binary tail (0.1 -> 0.1000000000000000055...) does
    # not leak into the stored value. Application (mypy-checked) callers pass Decimal;
    # this tolerates the float literals that test and fixture code write.
    return value if isinstance(value, Decimal) else Decimal(str(value))


def encode_money(value: Decimal | None) -> int | None:
    """Encode a ``Decimal`` money value to integer money minor units for storage."""
    if value is None:
        return None
    return to_minor_units(_as_decimal(value), MONEY_MINOR_UNITS_PER_DOLLAR)


def decode_money(units: int | None) -> Decimal | None:
    """Decode a stored integer money column to a ``Decimal`` money value."""
    if units is None:
        return None
    return from_minor_units(units, MONEY_MINOR_UNITS_PER_DOLLAR)


def encode_quantity(value: Decimal | None) -> int | None:
    """Encode a ``Decimal`` share quantity to integer quantity minor units for storage."""
    if value is None:
        return None
    return to_minor_units(_as_decimal(value), QUANTITY_MINOR_UNITS_PER_SHARE)


def decode_quantity(units: int | None) -> Decimal | None:
    """Decode a stored integer quantity column to a ``Decimal`` share quantity."""
    if units is None:
        return None
    return from_minor_units(units, QUANTITY_MINOR_UNITS_PER_SHARE)


# --- Row-boundary read helpers (mirror common.coercion.row_* for money columns) ---


def row_money(row: Mapping[str, object], key: str) -> Decimal | None:
    """Decode a stored integer money column from a row mapping to a ``Decimal``."""
    return decode_money(coerce_int(row[key]))


def row_expect_money(row: Mapping[str, object], key: str) -> Decimal:
    """Decode a non-null money column; raise if it is NULL."""
    result = row_money(row, key)
    if result is None:
        raise ValueError(f"{key} cannot be null")
    return result


def row_quantity(row: Mapping[str, object], key: str) -> Decimal | None:
    """Decode a stored integer quantity column from a row mapping to a ``Decimal``."""
    return decode_quantity(coerce_int(row[key]))


def row_expect_quantity(row: Mapping[str, object], key: str) -> Decimal:
    """Decode a non-null quantity column; raise if it is NULL."""
    result = row_quantity(row, key)
    if result is None:
        raise ValueError(f"{key} cannot be null")
    return result


def encode_columns(
    values: Mapping[str, object],
    *,
    money_columns: frozenset[str],
    quantity_columns: frozenset[str],
) -> dict[str, object]:
    """Return a copy of ``values`` with money and quantity columns encoded to integers.

    For the generic partial-update and field-derived-insert paths, where a mapping
    of column name to value mixes money, quantity, and plain columns. A ``Decimal``
    in a money or quantity column is encoded; every other value passes through.
    """
    encoded: dict[str, object] = {}
    for column, value in values.items():
        if column in money_columns:
            encoded[column] = encode_money(value)  # type: ignore[arg-type]
        elif column in quantity_columns:
            encoded[column] = encode_quantity(value)  # type: ignore[arg-type]
        else:
            encoded[column] = value
    return encoded
