import pytest

from trading.domain.rotation.schedule import (
    parse_rotation_schedule,
)


class TestParseRotationSchedule:
    @pytest.mark.parametrize(
        ("schedule", "expected"),
        [
            ('["trend","mean_reversion","trend"]', ["trend", "mean_reversion"]),
            (["trend", "macd"], ["trend", "macd"]),
        ],
    )
    def test_accepts_valid_json_and_list_inputs(self, schedule, expected) -> None:
        assert parse_rotation_schedule(schedule) == expected

    def test_rejects_invalid_structure_and_blank_strategy_name(self) -> None:
        with pytest.raises(ValueError):
            parse_rotation_schedule('{"bad": true}')
        with pytest.raises(ValueError):
            parse_rotation_schedule(["trend", ""])

    def test_rejects_unsupported_input_type(self) -> None:
        with pytest.raises(ValueError, match="must be a list or JSON string"):
            parse_rotation_schedule(123)

    def test_rejects_invalid_json(self) -> None:
        with pytest.raises(ValueError, match="must be valid JSON"):
            parse_rotation_schedule("[")

    def test_blank_string_returns_empty_schedule(self) -> None:
        assert parse_rotation_schedule("   ") == []
