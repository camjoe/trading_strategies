import pytest
from datetime import UTC, datetime

import trading.domain.rotation as rotation

from trading.domain.rotation import (
    OPTIMALITY_MODES,
    ROTATION_MODES,
    dump_rotation_schedule,
    is_rotation_due,
    next_rotation_state,
    parse_rotation_schedule,
    resolve_active_strategy,
    resolve_optimality_mode,
    resolve_rotation_mode,
)


def _due_account(**overrides):
    account = {
        "rotation_enabled": 1,
        "rotation_interval_days": 7,
        "rotation_schedule": dump_rotation_schedule(["trend", "mean_reversion"]),
        "rotation_last_at": "2026-03-01T00:00:00Z",
    }
    account.update(overrides)
    return account


class _IndexOnlyAccountMapping:
    def __init__(self, values):
        self._values = values

    def __getitem__(self, key):
        return self._values[key]


class _TypeErrorAccountMapping:
    def __getitem__(self, _key):
        raise TypeError("row unavailable")


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


class TestResolveModes:
    def test_resolve_rotation_mode_defaults_and_validation(self) -> None:
        assert ROTATION_MODES == {"time", "optimal"}
        assert resolve_rotation_mode({"rotation_mode": "optimal"}) == "optimal"
        assert resolve_rotation_mode({"rotation_mode": "TIME"}) == "time"
        assert resolve_rotation_mode({"rotation_mode": "unknown"}) == "time"

    def test_resolve_optimality_mode_defaults_and_validation(self) -> None:
        assert OPTIMALITY_MODES == {"previous_period_best", "average_return"}
        assert resolve_optimality_mode({"rotation_optimality_mode": "average_return"}) == "average_return"
        assert resolve_optimality_mode({"rotation_optimality_mode": "PREVIOUS_PERIOD_BEST"}) == "previous_period_best"
        assert resolve_optimality_mode({"rotation_optimality_mode": "unknown"}) == "previous_period_best"

    def test_resolve_rotation_mode_with_index_only_mapping(self) -> None:
        account = _IndexOnlyAccountMapping({"rotation_mode": "optimal"})

        assert resolve_rotation_mode(account) == "optimal"

    def test_resolve_rotation_mode_missing_key_defaults_when_key_error(self) -> None:
        account = _IndexOnlyAccountMapping({})

        assert resolve_rotation_mode(account) == "time"

    def test_resolve_optimality_mode_type_error_defaults(self) -> None:
        assert resolve_optimality_mode(_TypeErrorAccountMapping()) == "previous_period_best"


class TestIsRotationDue:
    @pytest.mark.parametrize(
        ("as_of_iso", "expected"),
        [
            ("2026-03-09T00:00:00Z", True),
            ("2026-03-05T00:00:00Z", False),
        ],
    )
    def test_interval_threshold_behavior(self, as_of_iso: str, expected: bool) -> None:
        assert is_rotation_due(_due_account(), as_of_iso=as_of_iso) is expected

    def test_raises_on_invalid_as_of_iso(self) -> None:
        with pytest.raises(ValueError, match="as_of_iso must be a valid ISO datetime"):
            is_rotation_due(_due_account(), as_of_iso="not-an-iso")

    def test_returns_true_when_last_rotation_unset(self) -> None:
        assert is_rotation_due(_due_account(rotation_last_at=""), as_of_iso="2026-03-09T00:00:00Z") is True

    def test_returns_false_when_not_enabled(self) -> None:
        assert is_rotation_due(_due_account(rotation_enabled=0), as_of_iso="2026-03-09T00:00:00Z") is False

    def test_returns_false_for_short_schedule(self) -> None:
        account = _due_account(rotation_schedule=dump_rotation_schedule(["trend"]))

        assert is_rotation_due(account, as_of_iso="2026-03-09T00:00:00Z") is False

    def test_returns_false_when_interval_missing_or_non_positive(self) -> None:
        missing_interval = _due_account()
        missing_interval.pop("rotation_interval_days")
        non_positive_interval = _due_account(rotation_interval_days=0)

        assert is_rotation_due(missing_interval, as_of_iso="2026-03-09T00:00:00Z") is False
        assert is_rotation_due(non_positive_interval, as_of_iso="2026-03-09T00:00:00Z") is False


class TestNextRotationState:
    def test_advances_index_and_strategy_for_longer_schedule(self) -> None:
        account = {
            "rotation_schedule": dump_rotation_schedule(["trend", "mean_reversion", "breakout"]),
            "rotation_active_index": 1,
        }

        nxt = next_rotation_state(account, as_of_iso="2026-03-17T12:00:00Z")

        assert nxt["rotation_active_index"] == 2
        assert nxt["rotation_active_strategy"] == "breakout"
        assert str(nxt["rotation_last_at"]).startswith("2026-03-17T12:00:00")

    def test_with_short_schedule_uses_resolved_active(self) -> None:
        account = {
            "strategy": "trend",
            "rotation_schedule": dump_rotation_schedule(["trend"]),
            "rotation_last_at": "2026-02-01T00:00:00Z",
        }

        state = next_rotation_state(account, as_of_iso="2026-03-10T00:00:00Z")

        assert state == {
            "rotation_active_index": 0,
            "rotation_active_strategy": "trend",
            "rotation_last_at": "2026-02-01T00:00:00Z",
        }

    def test_uses_now_when_as_of_iso_invalid(self, monkeypatch: pytest.MonkeyPatch) -> None:
        account = {
            "rotation_schedule": dump_rotation_schedule(["trend", "mean_reversion"]),
            "rotation_active_index": 0,
            "rotation_last_at": "2026-02-01T00:00:00Z",
        }

        class _FixedDateTime:
            @classmethod
            def now(cls, _tz):
                return datetime(2026, 3, 31, 9, 15, 0, tzinfo=UTC)

        monkeypatch.setattr(rotation, "_parse_iso", lambda _value: None)
        monkeypatch.setattr(rotation, "datetime", _FixedDateTime)

        state = next_rotation_state(account, as_of_iso="invalid")

        assert state["rotation_active_index"] == 1
        assert state["rotation_active_strategy"] == "mean_reversion"
        assert state["rotation_last_at"] == "2026-03-31T09:15:00Z"


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
        rendered = rotation._as_utc_iso(datetime(2026, 3, 10, 12, 30, 45, tzinfo=UTC))

        assert rendered == "2026-03-10T12:30:45Z"
