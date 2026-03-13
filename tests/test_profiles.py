from trading.accounts import get_account
from trading.profiles import apply_account_profiles


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
