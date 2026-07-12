from __future__ import annotations

import json

import pytest

from trading.repositories.strategies import StrategyRepository
from trading.services.strategy_catalog import (
    UnknownCatalogStrategyError,
    resolve_catalog_params,
    resolve_catalog_strategy,
    seed_strategy_catalog,
)

NOW = "2026-07-12T12:00:00Z"


def _insert_strategy(conn, *, strategy_key, primitive, params_json, style="neutral"):
    return StrategyRepository(conn).insert(
        strategy_key=strategy_key,
        primitive=primitive,
        params_json=params_json,
        style=style,
        created_at=NOW,
        updated_at=NOW,
    )


def test_seeded_strategy_resolves_to_primitive_defaults(conn) -> None:
    seed_strategy_catalog(conn, now_iso=NOW)

    params = resolve_catalog_params(conn, "trend")

    assert params == {"fast_window": 10, "slow_window": 20}


def test_resolve_is_case_insensitive_on_key(conn) -> None:
    seed_strategy_catalog(conn, now_iso=NOW)

    assert resolve_catalog_params(conn, "  TREND ") == {"fast_window": 10, "slow_window": 20}


def test_params_json_overrides_layer_over_primitive_defaults(conn) -> None:
    # A tuned variant of the trend primitive that only overrides one knob.
    _insert_strategy(
        conn,
        strategy_key="trend_fast",
        primitive="trend",
        params_json=json.dumps({"fast_window": 5}),
        style="trend",
    )

    resolved = resolve_catalog_strategy(conn, "trend_fast")

    assert resolved.primitive == "trend"
    # Overridden knob wins; the untouched knob keeps the primitive default.
    assert resolved.params == {"fast_window": 5, "slow_window": 20}


def test_empty_params_json_yields_primitive_defaults(conn) -> None:
    _insert_strategy(conn, strategy_key="trend_bare", primitive="trend", params_json="{}", style="trend")

    assert resolve_catalog_params(conn, "trend_bare") == {"fast_window": 10, "slow_window": 20}


def test_resolve_returns_a_fresh_dict_each_call(conn) -> None:
    seed_strategy_catalog(conn, now_iso=NOW)

    params = resolve_catalog_params(conn, "trend")
    params["fast_window"] = 1

    assert resolve_catalog_params(conn, "trend")["fast_window"] == 10


def test_missing_row_raises_unknown_catalog_strategy(conn) -> None:
    with pytest.raises(UnknownCatalogStrategyError):
        resolve_catalog_params(conn, "no_such_strategy")


def test_noncanonical_primitive_falls_back_to_registry_defaults(conn) -> None:
    # The label bridge mints draft rows whose primitive is the raw alias label
    # (P6-1 transitional). "meanrev" is not a canonical primitive id, but it
    # resolves leniently to the mean_reversion primitive's defaults.
    _insert_strategy(conn, strategy_key="meanrev", primitive="meanrev", params_json="{}")

    assert resolve_catalog_params(conn, "meanrev") == {"window": 20, "band_pct": 0.02}


def test_unresolvable_primitive_and_key_yields_empty_params(conn) -> None:
    _insert_strategy(conn, strategy_key="zzz_unknown", primitive="zzz_unknown", params_json="{}")

    assert resolve_catalog_params(conn, "zzz_unknown") == {}
