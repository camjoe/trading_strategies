from __future__ import annotations

from decimal import Decimal

import pytest

from common.constants import MONEY_MINOR_UNITS_PER_DOLLAR, QUANTITY_MINOR_UNITS_PER_SHARE
from trading.persistence.money_columns import (
    decode_money,
    decode_quantity,
    encode_money,
    encode_quantity,
    snap_money,
)


class TestMoneyColumn:
    def test_encodes_a_decimal_to_money_minor_units(self) -> None:
        assert encode_money(Decimal("12.34")) == 12_340_000

    def test_passes_none_through_on_encode(self) -> None:
        assert encode_money(None) is None

    def test_passes_none_through_on_decode(self) -> None:
        assert decode_money(None) is None

    def test_uses_the_money_scale(self) -> None:
        assert encode_money(Decimal("1")) == MONEY_MINOR_UNITS_PER_DOLLAR

    def test_round_trips_a_money_value(self) -> None:
        assert decode_money(encode_money(Decimal("999.999999"))) == Decimal("999.999999")


class TestQuantityColumn:
    def test_encodes_a_fractional_share_quantity(self) -> None:
        assert encode_quantity(Decimal("1.5")) == 1_500_000

    def test_uses_the_quantity_scale(self) -> None:
        assert encode_quantity(Decimal("1")) == QUANTITY_MINOR_UNITS_PER_SHARE

    @pytest.mark.parametrize("value", [Decimal("0.001"), Decimal("2.5"), Decimal("100")])
    def test_round_trips_a_fractional_quantity(self, value: Decimal) -> None:
        assert decode_quantity(encode_quantity(value)) == value


class TestSnapMoney:
    def test_truncates_a_finer_value_to_the_money_grid(self) -> None:
        assert snap_money(Decimal("33.51663315")) == Decimal("33.516633")

    def test_leaves_a_grid_value_unchanged(self) -> None:
        assert snap_money(Decimal("12.34")) == Decimal("12.34")

    @pytest.mark.parametrize("value", [Decimal("33.51663315"), Decimal("-0.0000005"), Decimal("100.55")])
    def test_equals_encode_then_decode(self, value: Decimal) -> None:
        # snap_money is the Decimal-in, Decimal-out form of a storage round trip.
        assert snap_money(value) == decode_money(encode_money(value))
