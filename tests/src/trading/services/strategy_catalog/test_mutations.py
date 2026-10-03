from __future__ import annotations

import json

import pytest

from trading.domain.exceptions import NotFoundError
from trading.repositories.strategies import StrategyImmutableError
from trading.services.strategy_catalog.mutations import configure_strategy, create_strategy_variant, freeze_strategy

NOW = "2026-07-12T00:00:00Z"


def test_create_variant_normalizes_key_and_stores_validated_overrides(conn) -> None:
    record = create_strategy_variant(
        conn,
        strategy_key="Trend_Fast",
        primitive="trend",
        params={"fast_window": "5"},
        now_iso=NOW,
    )

    assert record.strategy_key == "trend_fast"
    assert record.primitive == "trend"
    assert record.status == "draft"
    assert json.loads(record.params_json) == {"fast_window": 5}


def test_create_variant_rejects_unknown_primitive(conn) -> None:
    with pytest.raises(ValueError, match="Unknown signal primitive"):
        create_strategy_variant(conn, strategy_key="x", primitive="nope", now_iso=NOW)


def test_create_variant_rejects_invalid_knob(conn) -> None:
    with pytest.raises(ValueError, match="Unknown knob"):
        create_strategy_variant(conn, strategy_key="x", primitive="trend", params={"nope": 1}, now_iso=NOW)


def test_create_variant_rejects_duplicate_key(conn) -> None:
    create_strategy_variant(conn, strategy_key="trend_fast", primitive="trend", now_iso=NOW)

    with pytest.raises(ValueError, match="already exists"):
        create_strategy_variant(conn, strategy_key="trend_fast", primitive="trend", now_iso=NOW)


def test_configure_strategy_merges_knobs_over_existing(conn) -> None:
    create_strategy_variant(conn, strategy_key="trend_fast", primitive="trend", params={"fast_window": 5}, now_iso=NOW)

    record = configure_strategy(conn, strategy_key="trend_fast", params={"slow_window": 30}, now_iso=NOW)

    assert json.loads(record.params_json) == {"fast_window": 5, "slow_window": 30}


def test_configure_strategy_toggles_enabled(conn) -> None:
    create_strategy_variant(conn, strategy_key="trend_fast", primitive="trend", now_iso=NOW)

    record = configure_strategy(conn, strategy_key="trend_fast", enabled=False, now_iso=NOW)

    assert record.enabled == 0


def test_configure_missing_strategy_raises(conn) -> None:
    with pytest.raises(NotFoundError):
        configure_strategy(conn, strategy_key="nope", enabled=True, now_iso=NOW)


def test_frozen_strategy_rejects_knob_edit(conn) -> None:
    create_strategy_variant(conn, strategy_key="trend_fast", primitive="trend", now_iso=NOW)

    frozen = freeze_strategy(conn, strategy_key="trend_fast", now_iso=NOW)
    assert frozen.status == "frozen"

    with pytest.raises(StrategyImmutableError):
        configure_strategy(conn, strategy_key="trend_fast", params={"fast_window": 5}, now_iso=NOW)


def test_freeze_missing_strategy_raises(conn) -> None:
    with pytest.raises(NotFoundError):
        freeze_strategy(conn, strategy_key="nope", now_iso=NOW)
