from __future__ import annotations

from paper_trading_ui.backend.account_contract import (
    build_account_params_update_command,
    build_admin_create_account_command,
)
from paper_trading_ui.backend.schemas import AccountParamsRequest, AdminCreateAccountRequest


def test_build_admin_create_account_command_maps_account_config_and_rotation_fields() -> None:
    payload = AdminCreateAccountRequest(
        name="  acct_admin  ",
        strategy="  trend  ",
        initialCash=5000.0,
        descriptiveName="  Growth Account  ",
        optionType="  call  ",
        rotationEnabled=True,
        rotationMode="regime",
        rotationIntervalDays=7,
        rotationSchedule=["trend"],
        rotationRegimeStrategyRiskOn="trend",
        rotationRegimeStrategyNeutral="trend",
        rotationRegimeStrategyRiskOff="trend",
    )

    command = build_admin_create_account_command(payload)

    assert command.name == "acct_admin"
    assert command.strategy == "trend"
    assert command.benchmark_ticker == "SPY"
    assert command.config.descriptive_name == "Growth Account"
    assert command.config.option_type == "call"
    assert command.rotation_profile["rotation_enabled"] is True
    assert command.rotation_profile["rotation_mode"] == "regime"
    assert command.rotation_profile["rotation_interval_days"] == 7


def test_build_account_params_update_command_omits_absent_fields_and_keeps_falsey_values() -> None:
    body = AccountParamsRequest(
        strategy="  mean_reversion  ",
        descriptiveName="   ",
        learningEnabled=False,
        optionType="   ",
        rotationActiveIndex=0,
        rotationOverlayWatchlist=["AAPL", "MSFT"],
    )

    command = build_account_params_update_command(body)

    assert command.strategy == "mean_reversion"
    assert command.config_values["descriptive_name"] is None
    assert command.config.learning_enabled is False
    assert command.config.option_type is None
    assert "rotation_mode" not in command.rotation_profile
    assert command.rotation_profile["rotation_active_index"] == 0
    assert command.rotation_profile["rotation_overlay_watchlist"] == ["AAPL", "MSFT"]
