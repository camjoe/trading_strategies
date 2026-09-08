from __future__ import annotations

import pytest

from trading.interfaces.runtime.jobs.daily.paper_trading import caps as module


def test_parse_account_trade_caps_accepts_maximum_overrides() -> None:
    assert module.parse_account_trade_caps("momentum_5k:5,acct_b:3") == {"momentum_5k": 5, "acct_b": 3}


def test_parse_account_trade_caps_rejects_invalid_or_non_positive_values() -> None:
    with pytest.raises(ValueError, match="account:max"):
        module.parse_account_trade_caps("acct1-5")
    with pytest.raises(ValueError, match="max trades must be >= 1"):
        module.parse_account_trade_caps("acct:0")


def test_resolve_trade_caps_precedence_and_defaults() -> None:
    result = module.resolve_trade_caps(
        ["override", "primary", "other"],
        primary_accounts={"primary"},
        primary_max_trades=5,
        other_max_trades=11,
        account_trade_cap_overrides={"override": 3},
    )

    assert result == {"override": 3, "primary": 5, "other": 11}


def test_group_accounts_by_caps() -> None:
    assert module.group_accounts_by_caps(["a", "b", "c"], {"a": 5, "b": 11, "c": 5}) == {
        5: ["a", "c"],
        11: ["b"],
    }
