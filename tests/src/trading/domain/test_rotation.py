from datetime import UTC, datetime

import pytest

from common.time import as_utc_iso
import trading.domain.rotation as rotation
from trading.domain.rotation import (
    dump_rotation_schedule,
    parse_rotation_schedule,
    resolve_active_strategy,
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


class TestResolveActiveStrategy:
    def test_prefers_strategy_from_rotation_state(self) -> None:
        account = {
            "strategy": "trend",
            "rotation_schedule": '["trend","mean_reversion"]',
            "rotation_active_index": 1,
            "rotation_active_strategy": "mean_reversion",
        }

        assert resolve_active_strategy(account) == "mean_reversion"

    def test_falls_back_to_primary_strategy_without_schedule(self) -> None:
        account = {"strategy": "trend", "rotation_schedule": None, "rotation_active_strategy": ""}

        assert resolve_active_strategy(account) == "trend"

    def test_uses_modulo_index_when_active_strategy_mismatch(self) -> None:
        account = {
            "strategy": "trend",
            "rotation_schedule": dump_rotation_schedule(["trend", "mean_reversion"]),
            "rotation_active_strategy": "unknown",
            "rotation_active_index": 3,
        }

        assert resolve_active_strategy(account) == "mean_reversion"


class TestRotationTimeAndGuardrails:
    def test_parse_iso_handles_utc_suffix_and_naive_datetime(self) -> None:
        parsed_utc = rotation._parse_iso("2026-03-10T12:30:00Z")
        parsed_naive = rotation._parse_iso("2026-03-10T12:30:00")

        assert parsed_utc is not None
        assert parsed_utc.tzinfo is not None
        assert parsed_utc.tzinfo == UTC

        assert parsed_naive is not None
        assert parsed_naive.tzinfo is not None
        assert parsed_naive.tzinfo == UTC

    def test_parse_iso_returns_none_for_blank_and_invalid_values(self) -> None:
        assert rotation._parse_iso(None) is None
        assert rotation._parse_iso("   ") is None
        assert rotation._parse_iso("not-an-iso") is None

    def test_as_utc_iso_normalizes_output(self) -> None:
        rendered = as_utc_iso(datetime(2026, 3, 10, 12, 30, 45, tzinfo=UTC))

        assert rendered == "2026-03-10T12:30:45Z"
