"""Scale conversion between an exact ``Decimal`` and integer minor units.

The domain computes money and quantity with ``decimal.Decimal`` for exact
arithmetic; the database stores integer minor units at a fixed scale. These
helpers are the one place that crosses between the two, so the rounding rule
lives here and nowhere else.

The module is pure scale math with no domain dependency. It lives in ``common``
because both ``trading/domain`` and ``trading/persistence`` need it, and the
domain may not import the persistence layer (ADR 020: ``common`` keeps unit
scales).
"""

from __future__ import annotations

import decimal
from decimal import Decimal

# Truncate toward zero to the minor unit. One swappable policy for every
# conversion; change this constant to change the rounding rule everywhere.
MONEY_ROUNDING = decimal.ROUND_DOWN


def to_minor_units(value: Decimal, units_per_whole: int) -> int:
    """Convert a whole-unit ``Decimal`` to integer minor units, truncated toward zero."""
    scaled = value * units_per_whole
    return int(scaled.to_integral_value(rounding=MONEY_ROUNDING))


def from_minor_units(units: int, units_per_whole: int) -> Decimal:
    """Convert integer minor units back to a whole-unit ``Decimal``."""
    return Decimal(units) / Decimal(units_per_whole)


def truncate_to_scale(value: Decimal, units_per_whole: int) -> Decimal:
    """Snap a ``Decimal`` to the minor-unit grid, truncated toward zero.

    Use this for a domain division or a percentage sizing result that must land on
    the storage grid before it is used. It applies the same rounding rule as
    ``to_minor_units`` but returns a ``Decimal``, so callers do not scatter raw
    ``int()`` truncations.
    """
    return from_minor_units(to_minor_units(value, units_per_whole), units_per_whole)
