from __future__ import annotations

import json

from trading.persistence.json_columns import dumps_json_column


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
