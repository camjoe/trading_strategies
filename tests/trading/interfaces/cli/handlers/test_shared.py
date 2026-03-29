from __future__ import annotations

import types

import pytest

from trading.interfaces.cli.handlers.shared import (
    common_account_config_kwargs,
    resolve_learning_enabled,
)


def _args(**kwargs) -> types.SimpleNamespace:
    defaults = dict(
        learning_enabled=False,
        learning_disabled=False,
        display_name=None,
        goal_min_return_pct=None,
        goal_max_return_pct=None,
        goal_period=None,
        risk_policy=None,
        stop_loss_pct=None,
        take_profit_pct=None,
        instrument_mode=None,
        option_strike_offset_pct=None,
        option_min_dte=None,
        option_max_dte=None,
        option_type=None,
        target_delta_min=None,
        target_delta_max=None,
        max_premium_per_trade=None,
        max_contracts_per_trade=None,
        iv_rank_min=None,
        iv_rank_max=None,
        roll_dte_threshold=None,
        profit_take_pct=None,
        max_loss_pct=None,
    )
    defaults.update(kwargs)
    return types.SimpleNamespace(**defaults)


def test_resolve_learning_enabled_returns_true_when_flag_set() -> None:
    assert resolve_learning_enabled(_args(learning_enabled=True), include_learning_disabled=True) is True


def test_resolve_learning_enabled_returns_false_when_disabled_flag_set() -> None:
    assert resolve_learning_enabled(_args(learning_disabled=True), include_learning_disabled=True) is False


def test_resolve_learning_enabled_raises_when_both_flags_set() -> None:
    with pytest.raises(ValueError, match="Use only one"):
        resolve_learning_enabled(_args(learning_enabled=True, learning_disabled=True), include_learning_disabled=True)


def test_resolve_learning_enabled_returns_none_when_neither_set() -> None:
    assert resolve_learning_enabled(_args(), include_learning_disabled=True) is None


def test_resolve_learning_enabled_coerces_bool_when_include_disabled_false() -> None:
    assert resolve_learning_enabled(_args(learning_enabled=True), include_learning_disabled=False) is True
    assert resolve_learning_enabled(_args(learning_enabled=False), include_learning_disabled=False) is False


def test_common_account_config_kwargs_contains_all_expected_keys() -> None:
    result = common_account_config_kwargs(_args(display_name="My Acct"), include_learning_disabled=False)

    assert set(result.keys()) == {
        "descriptive_name",
        "goal_min_return_pct",
        "goal_max_return_pct",
        "goal_period",
        "learning_enabled",
        "risk_policy",
        "stop_loss_pct",
        "take_profit_pct",
        "instrument_mode",
        "option_strike_offset_pct",
        "option_min_dte",
        "option_max_dte",
        "option_type",
        "target_delta_min",
        "target_delta_max",
        "max_premium_per_trade",
        "max_contracts_per_trade",
        "iv_rank_min",
        "iv_rank_max",
        "roll_dte_threshold",
        "profit_take_pct",
        "max_loss_pct",
    }


def test_common_account_config_kwargs_maps_display_name_to_descriptive_name() -> None:
    result = common_account_config_kwargs(_args(display_name="Test Account"), include_learning_disabled=False)
    assert result["descriptive_name"] == "Test Account"
