import pytest

from trading.rotation import (
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


def test_parse_rotation_schedule_json_and_list() -> None:
    assert parse_rotation_schedule('["trend","mean_reversion","trend"]') == ["trend", "mean_reversion"]
    assert parse_rotation_schedule(["trend", "macd"]) == ["trend", "macd"]


def test_parse_rotation_schedule_validation() -> None:
    with pytest.raises(ValueError):
        parse_rotation_schedule('{"bad": true}')
    with pytest.raises(ValueError):
        parse_rotation_schedule(["trend", ""])


def test_resolve_active_strategy_prefers_rotation_state() -> None:
    account = {
        "strategy": "trend",
        "rotation_schedule": '["trend","mean_reversion"]',
        "rotation_active_index": 1,
        "rotation_active_strategy": "mean_reversion",
    }
    assert resolve_active_strategy(account) == "mean_reversion"


def test_is_rotation_due() -> None:
    account = {
        "rotation_enabled": 1,
        "rotation_interval_days": 7,
        "rotation_schedule": dump_rotation_schedule(["trend", "mean_reversion"]),
        "rotation_last_at": "2026-03-01T00:00:00Z",
    }
    assert is_rotation_due(account, as_of_iso="2026-03-09T00:00:00Z") is True
    assert is_rotation_due(account, as_of_iso="2026-03-05T00:00:00Z") is False


def test_next_rotation_state() -> None:
    account = {
        "rotation_schedule": dump_rotation_schedule(["trend", "mean_reversion", "breakout"]),
        "rotation_active_index": 1,
    }
    nxt = next_rotation_state(account, as_of_iso="2026-03-17T12:00:00Z")
    assert nxt["rotation_active_index"] == 2
    assert nxt["rotation_active_strategy"] == "breakout"
    assert str(nxt["rotation_last_at"]).startswith("2026-03-17T12:00:00")


def test_resolve_rotation_mode_defaults_and_validation() -> None:
    assert ROTATION_MODES == {"time", "optimal"}
    assert resolve_rotation_mode({"rotation_mode": "optimal"}) == "optimal"
    assert resolve_rotation_mode({"rotation_mode": "TIME"}) == "time"
    assert resolve_rotation_mode({"rotation_mode": "unknown"}) == "time"


def test_resolve_optimality_mode_defaults_and_validation() -> None:
    assert OPTIMALITY_MODES == {"previous_period_best", "average_return"}
    assert resolve_optimality_mode({"rotation_optimality_mode": "average_return"}) == "average_return"
    assert resolve_optimality_mode({"rotation_optimality_mode": "PREVIOUS_PERIOD_BEST"}) == "previous_period_best"
    assert resolve_optimality_mode({"rotation_optimality_mode": "unknown"}) == "previous_period_best"
