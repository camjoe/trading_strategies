import json

import pytest

from trading.accounts import get_account
from trading.db_coercion import coerce_bool
from trading.profiles import apply_account_profiles, load_account_profiles


def test_apply_account_profiles_sets_risk_and_instrument_fields(conn) -> None:
    profiles = [
        {
            "name": "prof_a",
            "strategy": "Momentum",
            "initial_cash": 5000,
            "benchmark_ticker": "SPY",
            "descriptive_name": "Profile A",
            "goal_min_return_pct": 2,
            "goal_max_return_pct": 5,
            "goal_period": "monthly",
            "learning_enabled": True,
            "risk_policy": "fixed_stop",
            "stop_loss_pct": 4,
            "instrument_mode": "leaps",
            "option_strike_offset_pct": 5,
            "option_min_dte": 120,
            "option_max_dte": 365,
            "option_type": "call",
            "target_delta_min": 0.25,
            "target_delta_max": 0.55,
            "max_premium_per_trade": 500,
            "max_contracts_per_trade": 2,
            "iv_rank_min": 20,
            "iv_rank_max": 80,
            "roll_dte_threshold": 45,
            "profit_take_pct": 30,
            "max_loss_pct": 20,
        }
    ]

    created, updated, skipped = apply_account_profiles(conn, profiles, create_missing=True)

    assert created == 1
    assert updated == 0
    assert skipped == 0

    account = get_account(conn, "prof_a")
    assert account["descriptive_name"] == "Profile A"
    assert account["risk_policy"] == "fixed_stop"
    assert account["instrument_mode"] == "leaps"
    assert int(account["learning_enabled"]) == 1
    assert account["option_type"] == "call"
    assert float(account["target_delta_min"]) == 0.25
    assert float(account["target_delta_max"]) == 0.55
    assert float(account["iv_rank_min"]) == 20.0
    assert float(account["iv_rank_max"]) == 80.0


# ---------------------------------------------------------------------------
# coerce_bool
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    (True, True), (False, False),
    (1, True), (0, False),
    ("true", True), ("yes", True), ("on", True), ("1", True),
    ("false", False), ("no", False), ("off", False), ("0", False),
    ("TRUE", True), ("YES", True),
])
def test_coerce_bool_valid(value, expected):
    assert coerce_bool(value) == expected


def test_coerce_bool_invalid_raises():
    with pytest.raises(ValueError):
        coerce_bool("maybe")


# ---------------------------------------------------------------------------
# load_account_profiles
# ---------------------------------------------------------------------------

def test_load_profiles_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_account_profiles(str(tmp_path / "missing.json"))


def test_load_profiles_list_format(tmp_path):
    f = tmp_path / "profiles.json"
    f.write_text(json.dumps([{"name": "acct1"}, {"name": "acct2"}]))
    profiles = load_account_profiles(str(f))
    assert [p["name"] for p in profiles] == ["acct1", "acct2"]


def test_load_profiles_dict_format(tmp_path):
    f = tmp_path / "profiles.json"
    f.write_text(json.dumps({"accounts": [{"name": "acct1"}]}))
    profiles = load_account_profiles(str(f))
    assert len(profiles) == 1
    assert profiles[0]["name"] == "acct1"


def test_load_profiles_non_list_raises(tmp_path):
    f = tmp_path / "profiles.json"
    f.write_text(json.dumps({"accounts": "not-a-list"}))
    with pytest.raises(ValueError, match="list"):
        load_account_profiles(str(f))


def test_load_profiles_non_dict_item_raises(tmp_path):
    f = tmp_path / "profiles.json"
    f.write_text(json.dumps([{"name": "ok"}, "bad"]))
    with pytest.raises(ValueError, match="not an object"):
        load_account_profiles(str(f))


def test_load_profiles_missing_name_raises(tmp_path):
    f = tmp_path / "profiles.json"
    f.write_text(json.dumps([{"strategy": "x"}]))
    with pytest.raises(ValueError, match="name"):
        load_account_profiles(str(f))


def test_load_profiles_empty_name_raises(tmp_path):
    f = tmp_path / "profiles.json"
    f.write_text(json.dumps([{"name": "   "}]))
    with pytest.raises(ValueError, match="name"):
        load_account_profiles(str(f))


# ---------------------------------------------------------------------------
# apply_account_profiles — branches not covered by the full-create test
# ---------------------------------------------------------------------------

def test_apply_create_missing_false_skips(conn):
    profiles = [{"name": "no_create", "initial_cash": 1000}]
    created, updated, skipped = apply_account_profiles(conn, profiles, create_missing=False)
    assert (created, updated, skipped) == (0, 0, 1)


def test_apply_create_uses_defaults(conn):
    """Minimal profile should receive sensible defaults for required fields."""
    profiles = [{"name": "minimal", "initial_cash": 1000}]
    created, _, _ = apply_account_profiles(conn, profiles, create_missing=True)
    assert created == 1
    account = get_account(conn, "minimal")
    assert account["goal_period"] == "monthly"
    assert account["risk_policy"] == "none"
    assert account["instrument_mode"] == "equity"
    assert int(account["learning_enabled"]) == 0


def test_apply_update_benchmark(conn):
    apply_account_profiles(conn, [{"name": "upd", "initial_cash": 1000}], create_missing=True)
    _, updated, _ = apply_account_profiles(
        conn, [{"name": "upd", "benchmark_ticker": "QQQ"}], create_missing=False
    )
    assert updated == 1
    assert get_account(conn, "upd")["benchmark_ticker"] == "QQQ"


def test_apply_update_strategy(conn):
    apply_account_profiles(conn, [{"name": "s_acct", "initial_cash": 1000}], create_missing=True)
    _, updated, _ = apply_account_profiles(
        conn, [{"name": "s_acct", "strategy": "ValuePlay"}], create_missing=False
    )
    assert updated == 1
    assert get_account(conn, "s_acct")["strategy"] == "ValuePlay"


def test_apply_update_configure_fields(conn):
    apply_account_profiles(conn, [{"name": "cfg", "initial_cash": 1000}], create_missing=True)
    _, updated, _ = apply_account_profiles(
        conn, [{"name": "cfg", "risk_policy": "fixed_stop", "stop_loss_pct": 5.0}], create_missing=False
    )
    assert updated == 1
    account = get_account(conn, "cfg")
    assert account["risk_policy"] == "fixed_stop"
    assert float(account["stop_loss_pct"]) == 5.0


def test_apply_no_op_skipped(conn):
    """Existing account with no recognized configurable keys → skipped."""
    apply_account_profiles(conn, [{"name": "noop", "initial_cash": 1000}], create_missing=True)
    _, updated, skipped = apply_account_profiles(
        conn, [{"name": "noop", "initial_cash": 9999}], create_missing=False
    )
    assert updated == 0
    assert skipped == 1
