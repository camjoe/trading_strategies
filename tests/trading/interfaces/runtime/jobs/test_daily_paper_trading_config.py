from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.support.runtime_jobs import daily_paper_trading as module


def test_parse_account_trade_caps_empty_string_returns_empty_dict() -> None:
    assert module.parse_account_trade_caps("") == {}

def test_parse_account_trade_caps_whitespace_only_returns_empty_dict() -> None:
    assert module.parse_account_trade_caps("   ") == {}

def test_parse_account_trade_caps_single_entry() -> None:
    result = module.parse_account_trade_caps("momentum_5k:1-5")
    assert result == {"momentum_5k": (1, 5)}

def test_parse_account_trade_caps_multiple_entries() -> None:
    result = module.parse_account_trade_caps("acct_a:2-8,acct_b:1-3")
    assert result == {"acct_a": (2, 8), "acct_b": (1, 3)}

def test_parse_account_trade_caps_missing_colon_raises() -> None:
    with pytest.raises(ValueError, match="account:min-max"):
        module.parse_account_trade_caps("acct1-5")

def test_parse_account_trade_caps_missing_dash_raises() -> None:
    with pytest.raises(ValueError, match="account:min-max"):
        module.parse_account_trade_caps("acct:15")

def test_parse_account_trade_caps_min_trades_below_one_raises() -> None:
    with pytest.raises(ValueError, match="min trades must be >= 1"):
        module.parse_account_trade_caps("acct:0-5")

def test_parse_account_trade_caps_max_less_than_min_raises() -> None:
    with pytest.raises(ValueError, match="max trades must be >= min trades"):
        module.parse_account_trade_caps("acct:5-2")


def test_load_trade_caps_config_missing_file_returns_none_and_empty(tmp_path: Path) -> None:
    default_caps, account_caps, excluded = module.load_trade_caps_config(tmp_path / "missing.json")
    assert default_caps is None
    assert account_caps == {}
    assert excluded == []

def test_load_trade_caps_config_valid_config_with_default_and_accounts(tmp_path: Path) -> None:
    config = {
        "default": {"min": 1, "max": 5},
        "accounts": {"special_acct": {"min": 2, "max": 8}},
    }
    path = tmp_path / "caps.json"
    path.write_text(json.dumps(config), encoding="utf-8")

    default_caps, account_caps, excluded = module.load_trade_caps_config(path)
    assert default_caps == (1, 5)
    assert account_caps == {"special_acct": (2, 8)}
    assert excluded == []

def test_load_trade_caps_config_without_default_returns_none(tmp_path: Path) -> None:
    path = tmp_path / "caps.json"
    path.write_text(json.dumps({"accounts": {}}), encoding="utf-8")
    default_caps, _, _excluded = module.load_trade_caps_config(path)
    assert default_caps is None

def test_load_trade_caps_config_excluded_accounts_are_returned(tmp_path: Path) -> None:
    config = {
        "excluded": ["test_account_bt", "sandbox"],
        "default": {"min": 1, "max": 5},
        "accounts": {},
    }
    path = tmp_path / "caps.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    _, _, excluded = module.load_trade_caps_config(path)
    assert excluded == ["test_account_bt", "sandbox"]

def test_load_trade_caps_config_non_dict_root_raises(tmp_path: Path) -> None:
    path = tmp_path / "caps.json"
    path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    with pytest.raises(ValueError, match="JSON object"):
        module.load_trade_caps_config(path)

def test_load_trade_caps_config_default_missing_min_raises(tmp_path: Path) -> None:
    path = tmp_path / "caps.json"
    path.write_text(json.dumps({"default": {"max": 5}}), encoding="utf-8")
    with pytest.raises(ValueError, match="min"):
        module.load_trade_caps_config(path)

def test_load_trade_caps_config_account_caps_not_dict_raises(tmp_path: Path) -> None:
    path = tmp_path / "caps.json"
    path.write_text(json.dumps({"accounts": "bad"}), encoding="utf-8")
    with pytest.raises(ValueError, match="object"):
        module.load_trade_caps_config(path)


def _resolve_trade_caps(accounts, **kwargs):
    defaults = {
        "configured_default_caps": None,
        "configured_account_caps": {},
        "primary_accounts": set(),
        "primary_min_trades": 1,
        "primary_max_trades": 5,
        "other_min_trades": 1,
        "other_max_trades": 11,
        "account_trade_cap_overrides": {},
    }
    defaults.update(kwargs)
    return module.resolve_trade_caps(accounts, **defaults)

def test_resolve_trade_caps_cli_override_takes_highest_priority() -> None:
    result = _resolve_trade_caps(
        ["acct"],
        configured_account_caps={"acct": (2, 8)},
        account_trade_cap_overrides={"acct": (3, 3)},
    )
    assert result["acct"] == (3, 3)

def test_resolve_trade_caps_configured_account_cap_used_when_no_override() -> None:
    result = _resolve_trade_caps(["acct"], configured_account_caps={"acct": (2, 7)})
    assert result["acct"] == (2, 7)

def test_resolve_trade_caps_configured_default_used_when_no_account_entry() -> None:
    result = _resolve_trade_caps(["acct"], configured_default_caps=(1, 6))
    assert result["acct"] == (1, 6)

def test_resolve_trade_caps_primary_account_uses_primary_limits() -> None:
    result = _resolve_trade_caps(
        ["primary_acct"],
        primary_accounts={"primary_acct"},
        primary_min_trades=2,
        primary_max_trades=4,
    )
    assert result["primary_acct"] == (2, 4)

def test_resolve_trade_caps_non_primary_uses_other_limits() -> None:
    result = _resolve_trade_caps(
        ["other_acct"],
        other_min_trades=1,
        other_max_trades=9,
    )
    assert result["other_acct"] == (1, 9)
