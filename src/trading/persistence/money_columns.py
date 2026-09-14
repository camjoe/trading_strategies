"""Encode and decode money and quantity columns at the repository boundary.

The repository layer crosses here on every read and write. A money or quantity
column stores an integer at a fixed scale; the domain holds a ``decimal.Decimal``.
These functions bind the pure ``common.money`` conversion to the two fixed scales,
so no repository hand-converts a value.

The persistence package imports nothing from ``trading`` or ``infrastructure``;
``common`` is below both, so it is allowed.
"""

from __future__ import annotations

from decimal import Decimal

from common.constants import MONEY_MINOR_UNITS_PER_DOLLAR, QUANTITY_MINOR_UNITS_PER_SHARE
from common.money import from_minor_units, to_minor_units


def encode_money(value: Decimal | None) -> int | None:
    """Encode a ``Decimal`` money value to integer money minor units for storage."""
    if value is None:
        return None
    return to_minor_units(value, MONEY_MINOR_UNITS_PER_DOLLAR)


def decode_money(units: int | None) -> Decimal | None:
    """Decode a stored integer money column to a ``Decimal`` money value."""
    if units is None:
        return None
    return from_minor_units(units, MONEY_MINOR_UNITS_PER_DOLLAR)


def encode_quantity(value: Decimal | None) -> int | None:
    """Encode a ``Decimal`` share quantity to integer quantity minor units for storage."""
    if value is None:
        return None
    return to_minor_units(value, QUANTITY_MINOR_UNITS_PER_SHARE)


def decode_quantity(units: int | None) -> Decimal | None:
    """Decode a stored integer quantity column to a ``Decimal`` share quantity."""
    if units is None:
        return None
    return from_minor_units(units, QUANTITY_MINOR_UNITS_PER_SHARE)
