from __future__ import annotations

import json

import pytest

from trading.persistence.json_columns import dumps_json_column, read_json_object


class TestDumpsJsonColumn:
    def test_same_data_in_a_different_key_order_produces_identical_text(self) -> None:
        # The property a hash over a stored payload depends on — see
        # params_fingerprint in the walk-forward optimizer.
        assert dumps_json_column({"b": 1, "a": 2}) == dumps_json_column({"a": 2, "b": 1})

    def test_carries_no_insignificant_whitespace(self) -> None:
        assert dumps_json_column({"a": 1, "b": [1, 2]}) == '{"a":1,"b":[1,2]}'

    def test_lists_round_trip_unreordered(self) -> None:
        # sort_keys is a no-op on a list: trade_symbols keeps its resolved order.
        assert dumps_json_column(["MSFT", "AAPL"]) == '["MSFT","AAPL"]'

    def test_round_trips_through_json_loads(self) -> None:
        payload = {"z": [1, 2], "a": {"nested": True}, "n": None}

        assert json.loads(dumps_json_column(payload)) == payload


class TestReadJsonObject:
    def test_missing_value_reads_as_an_empty_object(self) -> None:
        assert read_json_object({"payload": None}, "payload") == {}

    def test_decodes_an_object(self) -> None:
        assert read_json_object({"payload": '{"a":1}'}, "payload") == {"a": 1}

    @pytest.mark.parametrize("stored", ["[1, 2, 3]", '"text"', "7"])
    def test_rejects_any_shape_that_is_not_an_object(self, stored: str) -> None:
        with pytest.raises(ValueError, match="Expected a JSON object in column 'payload'"):
            read_json_object({"payload": stored}, "payload")
