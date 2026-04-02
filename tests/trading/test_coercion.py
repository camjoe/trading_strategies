import pytest

from trading.utils.coercion import coerce_bool


class TestCoerceBool:
    @pytest.mark.parametrize("value,expected", [
        (True, True), (False, False),
        (1, True), (0, False),
        ("true", True), ("yes", True), ("on", True), ("1", True),
        ("false", False), ("no", False), ("off", False), ("0", False),
        ("TRUE", True), ("YES", True),
    ])
    def test_valid_values(self, value, expected):
        assert coerce_bool(value) == expected

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            coerce_bool("maybe")
