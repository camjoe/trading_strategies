from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest


def _load():
    return importlib.import_module(
        "trading.interfaces.runtime.jobs.daily_paper_trading"
    )


# ---------------------------------------------------------------------------
# parse_account_trade_caps
# ---------------------------------------------------------------------------

class TestParseAccountTradeCaps:
    def test_empty_string_returns_empty_dict(self) -> None:
        assert _load().parse_account_trade_caps("") == {}

    def test_whitespace_only_returns_empty_dict(self) -> None:
        assert _load().parse_account_trade_caps("   ") == {}

    def test_single_entry(self) -> None:
        result = _load().parse_account_trade_caps("momentum_5k:1-5")
        assert result == {"momentum_5k": (1, 5)}

    def test_multiple_entries(self) -> None:
        result = _load().parse_account_trade_caps("acct_a:2-8,acct_b:1-3")
        assert result == {"acct_a": (2, 8), "acct_b": (1, 3)}

    def test_missing_colon_raises(self) -> None:
        with pytest.raises(ValueError, match="account:min-max"):
            _load().parse_account_trade_caps("acct1-5")

    def test_missing_dash_raises(self) -> None:
        with pytest.raises(ValueError, match="account:min-max"):
            _load().parse_account_trade_caps("acct:15")

    def test_min_trades_below_one_raises(self) -> None:
        with pytest.raises(ValueError, match="min trades must be >= 1"):
            _load().parse_account_trade_caps("acct:0-5")

    def test_max_less_than_min_raises(self) -> None:
        with pytest.raises(ValueError, match="max trades must be >= min trades"):
            _load().parse_account_trade_caps("acct:5-2")


# ---------------------------------------------------------------------------
# load_trade_caps_config
# ---------------------------------------------------------------------------

class TestLoadTradeCapsConfig:
    def test_missing_file_returns_none_and_empty(self, tmp_path: Path) -> None:
        default_caps, account_caps = _load().load_trade_caps_config(tmp_path / "missing.json")
        assert default_caps is None
        assert account_caps == {}

    def test_valid_config_with_default_and_accounts(self, tmp_path: Path) -> None:
        config = {
            "default": {"min": 1, "max": 5},
            "accounts": {
                "special_acct": {"min": 2, "max": 8},
            },
        }
        path = tmp_path / "caps.json"
        path.write_text(json.dumps(config), encoding="utf-8")

        default_caps, account_caps = _load().load_trade_caps_config(path)
        assert default_caps == (1, 5)
        assert account_caps == {"special_acct": (2, 8)}

    def test_config_without_default_returns_none(self, tmp_path: Path) -> None:
        path = tmp_path / "caps.json"
        path.write_text(json.dumps({"accounts": {}}), encoding="utf-8")
        default_caps, _ = _load().load_trade_caps_config(path)
        assert default_caps is None

    def test_non_dict_root_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "caps.json"
        path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        with pytest.raises(ValueError, match="JSON object"):
            _load().load_trade_caps_config(path)

    def test_default_missing_min_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "caps.json"
        path.write_text(json.dumps({"default": {"max": 5}}), encoding="utf-8")
        with pytest.raises(ValueError, match="min"):
            _load().load_trade_caps_config(path)

    def test_account_caps_not_dict_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "caps.json"
        path.write_text(json.dumps({"accounts": "bad"}), encoding="utf-8")
        with pytest.raises(ValueError, match="object"):
            _load().load_trade_caps_config(path)


# ---------------------------------------------------------------------------
# resolve_trade_caps
# ---------------------------------------------------------------------------

class TestResolveTradeCaps:
    def _resolve(self, accounts, **kwargs):
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
        return _load().resolve_trade_caps(accounts, **defaults)

    def test_cli_override_takes_highest_priority(self) -> None:
        result = self._resolve(
            ["acct"],
            configured_account_caps={"acct": (2, 8)},
            account_trade_cap_overrides={"acct": (3, 3)},
        )
        assert result["acct"] == (3, 3)

    def test_configured_account_cap_used_when_no_override(self) -> None:
        result = self._resolve(["acct"], configured_account_caps={"acct": (2, 7)})
        assert result["acct"] == (2, 7)

    def test_configured_default_used_when_no_account_entry(self) -> None:
        result = self._resolve(["acct"], configured_default_caps=(1, 6))
        assert result["acct"] == (1, 6)

    def test_primary_account_uses_primary_limits(self) -> None:
        result = self._resolve(
            ["primary_acct"],
            primary_accounts={"primary_acct"},
            primary_min_trades=2,
            primary_max_trades=4,
        )
        assert result["primary_acct"] == (2, 4)

    def test_non_primary_uses_other_limits(self) -> None:
        result = self._resolve(
            ["other_acct"],
            other_min_trades=1,
            other_max_trades=9,
        )
        assert result["other_acct"] == (1, 9)
