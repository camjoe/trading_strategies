from __future__ import annotations

from decimal import Decimal

import pytest

from common.money import from_minor_units, to_minor_units, truncate_to_scale

# A million minor units per whole unit, matching the provisional scale.
SCALE = 1_000_000


class TestToMinorUnits:
    def test_converts_a_whole_value(self) -> None:
        assert to_minor_units(Decimal("1.5"), SCALE) == 1_500_000

    def test_truncates_toward_zero_below_the_minor_unit(self) -> None:
        # 0.0000005 is half a minor unit at this scale; truncation drops it.
        assert to_minor_units(Decimal("0.0000005"), SCALE) == 0

    def test_truncates_a_negative_value_toward_zero(self) -> None:
        # Toward zero, not floor: -0.0000005 truncates to 0, not -1.
        assert to_minor_units(Decimal("-0.0000005"), SCALE) == 0

    def test_truncates_a_negative_whole_plus_dust_toward_zero(self) -> None:
        assert to_minor_units(Decimal("-1.5000005"), SCALE) == -1_500_000


class TestFromMinorUnits:
    def test_decodes_to_an_exact_decimal(self) -> None:
        assert from_minor_units(1_500_000, SCALE) == Decimal("1.5")

    @pytest.mark.parametrize("units", [0, 1, -1, 1_000_000, -2_500_000])
    def test_round_trips_through_to_minor_units(self, units: int) -> None:
        assert to_minor_units(from_minor_units(units, SCALE), SCALE) == units


class TestTruncateToScale:
    def test_snaps_a_finer_value_to_the_grid(self) -> None:
        assert truncate_to_scale(Decimal("1.23456789"), SCALE) == Decimal("1.234567")

    def test_leaves_a_grid_value_unchanged(self) -> None:
        assert truncate_to_scale(Decimal("2.5"), SCALE) == Decimal("2.5")
