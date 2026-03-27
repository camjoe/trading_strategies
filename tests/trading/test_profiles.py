import json

import pytest

from trading.accounts import get_account
from trading.coercion import coerce_bool
from trading.profiles import apply_account_profiles, load_account_profiles


class TestCoerceBool:
    @pytest.mark.parametrize("value,expected", [
        (True, True), (False, False),
        (1, True), (0, False),
        ("true", True), ("yes", True), ("on", True), ("1", True),
        ("false", False), ("no", False), ("off", False), ("0", False),
        ("TRUE", True), ("YES", True),
    ])
    def test_valid_values(self, value, expected):
        assert coerce_bool(value) == expected

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            coerce_bool("maybe")


class TestLoadAccountProfiles:
    def test_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_account_profiles(str(tmp_path / "missing.json"))

    def test_list_format(self, tmp_path):
        f = tmp_path / "profiles.json"
        f.write_text(json.dumps([{"name": "acct1"}, {"name": "acct2"}]))
        profiles = load_account_profiles(str(f))
        assert [p["name"] for p in profiles] == ["acct1", "acct2"]

    def test_dict_format(self, tmp_path):
        f = tmp_path / "profiles.json"
        f.write_text(json.dumps({"accounts": [{"name": "acct1"}]}))
        profiles = load_account_profiles(str(f))
        assert len(profiles) == 1
        assert profiles[0]["name"] == "acct1"

    def test_non_list_raises(self, tmp_path):
        f = tmp_path / "profiles.json"
        f.write_text(json.dumps({"accounts": "not-a-list"}))
        with pytest.raises(ValueError, match="list"):
            load_account_profiles(str(f))

    def test_non_dict_item_raises(self, tmp_path):
        f = tmp_path / "profiles.json"
        f.write_text(json.dumps([{"name": "ok"}, "bad"]))
        with pytest.raises(ValueError, match="not an object"):
            load_account_profiles(str(f))

    def test_missing_name_raises(self, tmp_path):
        f = tmp_path / "profiles.json"
        f.write_text(json.dumps([{"strategy": "x"}]))
        with pytest.raises(ValueError, match="name"):
            load_account_profiles(str(f))

    def test_empty_name_raises(self, tmp_path):
        f = tmp_path / "profiles.json"
        f.write_text(json.dumps([{"name": "   "}]))
        with pytest.raises(ValueError, match="name"):
            load_account_profiles(str(f))


class TestApplyAccountProfiles:
    def test_sets_risk_and_instrument_fields(self, conn) -> None:
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

    def test_create_missing_false_skips(self, conn):
        profiles = [{"name": "no_create", "initial_cash": 1000}]
        created, updated, skipped = apply_account_profiles(conn, profiles, create_missing=False)
        assert (created, updated, skipped) == (0, 0, 1)

    def test_create_uses_defaults(self, conn):
        """Minimal profile should receive sensible defaults for required fields."""
        profiles = [{"name": "minimal", "initial_cash": 1000}]
        created, _, _ = apply_account_profiles(conn, profiles, create_missing=True)
        assert created == 1
        account = get_account(conn, "minimal")
        assert account["goal_period"] == "monthly"
        assert account["risk_policy"] == "none"
        assert account["instrument_mode"] == "equity"
        assert int(account["learning_enabled"]) == 0

    def test_update_benchmark(self, conn):
        apply_account_profiles(conn, [{"name": "upd", "initial_cash": 1000}], create_missing=True)
        _, updated, _ = apply_account_profiles(
            conn, [{"name": "upd", "benchmark_ticker": "QQQ"}], create_missing=False
        )
        assert updated == 1
        assert get_account(conn, "upd")["benchmark_ticker"] == "QQQ"

    def test_update_strategy(self, conn):
        apply_account_profiles(conn, [{"name": "s_acct", "initial_cash": 1000}], create_missing=True)
        _, updated, _ = apply_account_profiles(
            conn, [{"name": "s_acct", "strategy": "ValuePlay"}], create_missing=False
        )
        assert updated == 1
        assert get_account(conn, "s_acct")["strategy"] == "ValuePlay"

    def test_update_configure_fields(self, conn):
        apply_account_profiles(conn, [{"name": "cfg", "initial_cash": 1000}], create_missing=True)
        _, updated, _ = apply_account_profiles(
            conn, [{"name": "cfg", "risk_policy": "fixed_stop", "stop_loss_pct": 5.0}], create_missing=False
        )
        assert updated == 1
        account = get_account(conn, "cfg")
        assert account["risk_policy"] == "fixed_stop"
        assert float(account["stop_loss_pct"]) == 5.0

    def test_no_op_skipped(self, conn):
        """Existing account with no recognized configurable keys -> skipped."""
        apply_account_profiles(conn, [{"name": "noop", "initial_cash": 1000}], create_missing=True)
        _, updated, skipped = apply_account_profiles(
            conn, [{"name": "noop", "initial_cash": 9999}], create_missing=False
        )
        assert updated == 0
        assert skipped == 1

    def test_rejects_null_initial_cash(self, conn):
        with pytest.raises(ValueError, match="initial_cash cannot be null"):
            apply_account_profiles(conn, [{"name": "null_cash", "initial_cash": None}], create_missing=True)


class TestApplyRotationFields:
    def test_created_account(self, conn):
        profiles = [
            {
                "name": "rot_new",
                "strategy": "trend",
                "initial_cash": 2500,
                "rotation_enabled": True,
                "rotation_interval_days": 7,
                "rotation_schedule": ["trend", "mean_reversion"],
                "rotation_active_index": 1,
                "rotation_last_at": "2026-03-01T00:00:00Z",
            }
        ]

        created, updated, skipped = apply_account_profiles(conn, profiles, create_missing=True)
        assert (created, updated, skipped) == (1, 0, 0)

        account = get_account(conn, "rot_new")
        assert int(account["rotation_enabled"]) == 1
        assert int(account["rotation_interval_days"]) == 7
        assert account["rotation_schedule"] == "[\"trend\",\"mean_reversion\"]"
        assert int(account["rotation_active_index"]) == 1
        assert account["rotation_last_at"] == "2026-03-01T00:00:00Z"
        assert account["rotation_active_strategy"] == "mean_reversion"

    def test_existing_account(self, conn):
        apply_account_profiles(conn, [{"name": "rot_upd", "initial_cash": 1000}], create_missing=True)

        created, updated, skipped = apply_account_profiles(
            conn,
            [
                {
                    "name": "rot_upd",
                    "rotation_enabled": True,
                    "rotation_interval_days": 14,
                    "rotation_schedule": ["trend", "breakout", "mean_reversion"],
                    "rotation_active_strategy": "breakout",
                }
            ],
            create_missing=False,
        )

        assert (created, updated, skipped) == (0, 1, 0)
        account = get_account(conn, "rot_upd")
        assert int(account["rotation_enabled"]) == 1
        assert int(account["rotation_interval_days"]) == 14
        assert account["rotation_schedule"] == "[\"trend\",\"breakout\",\"mean_reversion\"]"
        assert account["rotation_active_strategy"] == "breakout"

    def test_optimal_fields(self, conn):
        apply_account_profiles(conn, [{"name": "rot_opt", "initial_cash": 1000}], create_missing=True)

        created, updated, skipped = apply_account_profiles(
            conn,
            [
                {
                    "name": "rot_opt",
                    "rotation_enabled": True,
                    "rotation_interval_days": 7,
                    "rotation_schedule": ["trend", "mean_reversion"],
                    "rotation_mode": "optimal",
                    "rotation_optimality_mode": "average_return",
                    "rotation_lookback_days": 90,
                }
            ],
            create_missing=False,
        )

        assert (created, updated, skipped) == (0, 1, 0)
        account = get_account(conn, "rot_opt")
        assert account["rotation_mode"] == "optimal"
        assert account["rotation_optimality_mode"] == "average_return"
        assert int(account["rotation_lookback_days"]) == 90

    def test_rejects_zero_interval_days(self, conn):
        with pytest.raises(ValueError, match="rotation_interval_days"):
            apply_account_profiles(
                conn,
                [{"name": "bad_rot", "initial_cash": 1000, "rotation_enabled": True, "rotation_interval_days": 0}],
                create_missing=True,
            )

    def test_rejects_active_strategy_not_in_schedule(self, conn):
        apply_account_profiles(conn, [{"name": "bad_rot2", "initial_cash": 1000}], create_missing=True)
        with pytest.raises(ValueError, match="rotation_active_strategy"):
            apply_account_profiles(
                conn,
                [
                    {
                        "name": "bad_rot2",
                        "rotation_schedule": ["trend", "mean_reversion"],
                        "rotation_active_strategy": "macd",
                    }
                ],
                create_missing=False,
            )

    def test_rejects_invalid_mode(self, conn):
        with pytest.raises(ValueError, match="rotation_mode"):
            apply_account_profiles(
                conn,
                [{"name": "bad_rot_mode", "initial_cash": 1000, "rotation_mode": "regime"}],
                create_missing=True,
            )

    def test_rejects_invalid_optimality_mode(self, conn):
        with pytest.raises(ValueError, match="rotation_optimality_mode"):
            apply_account_profiles(
                conn,
                [
                    {
                        "name": "bad_rot_opt",
                        "initial_cash": 1000,
                        "rotation_optimality_mode": "median_return",
                    }
                ],
                create_missing=True,
            )

    def test_rejects_zero_lookback_days(self, conn):
        with pytest.raises(ValueError, match="rotation_lookback_days"):
            apply_account_profiles(
                conn,
                [{"name": "bad_rot_lookback", "initial_cash": 1000, "rotation_lookback_days": 0}],
                create_missing=True,
            )

    def test_rejects_negative_active_index(self, conn):
        with pytest.raises(ValueError, match="rotation_active_index"):
            apply_account_profiles(
                conn,
                [{"name": "bad_rot_index", "initial_cash": 1000, "rotation_active_index": -1}],
                create_missing=True,
            )

    def test_index_normalized_to_schedule_length(self, conn):
        apply_account_profiles(conn, [{"name": "rot_mod", "initial_cash": 1000}], create_missing=True)

        created, updated, skipped = apply_account_profiles(
            conn,
            [
                {
                    "name": "rot_mod",
                    "rotation_schedule": ["trend", "breakout"],
                    "rotation_active_index": 5,
                }
            ],
            create_missing=False,
        )

        assert (created, updated, skipped) == (0, 1, 0)
        account = get_account(conn, "rot_mod")
        assert int(account["rotation_active_index"]) == 1
        assert account["rotation_active_strategy"] == "breakout"

    def test_only_active_strategy_updates_field(self, conn):
        apply_account_profiles(conn, [{"name": "rot_noop", "initial_cash": 1000}], create_missing=True)

        created, updated, skipped = apply_account_profiles(
            conn,
            [{"name": "rot_noop", "rotation_active_strategy": "trend"}],
            create_missing=False,
        )

        assert (created, updated, skipped) == (0, 1, 0)
        account = get_account(conn, "rot_noop")
        assert account["rotation_active_strategy"] == "trend"

    def test_only_mode_updates_mode(self, conn):
        apply_account_profiles(conn, [{"name": "rot_mode_only", "initial_cash": 1000}], create_missing=True)

        created, updated, skipped = apply_account_profiles(
            conn,
            [{"name": "rot_mode_only", "rotation_mode": "optimal"}],
            create_missing=False,
        )

        assert (created, updated, skipped) == (0, 1, 0)
        account = get_account(conn, "rot_mode_only")
        assert account["rotation_mode"] == "optimal"
