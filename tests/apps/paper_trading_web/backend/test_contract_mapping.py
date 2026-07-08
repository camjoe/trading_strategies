from __future__ import annotations

from paper_trading_web.backend.account_contract import (
    build_account_params_update_command,
    build_admin_create_account_command,
)
from paper_trading_web.backend.schemas import AccountParamsRequest, AdminCreateAccountRequest


def test_build_admin_create_account_command_maps_account_config_and_rotation_fields() -> None:
    payload = AdminCreateAccountRequest(
        name="  acct_admin  ",
        strategy="  trend  ",
        initialCash=5000.0,
        accountKind=" local ",
        descriptiveName="  Growth Account  ",
        optionType="  call  ",
        rotationEnabled=True,
        rotationIntervalDays=7,
        rotationSchedule=["trend"],
    )

    command = build_admin_create_account_command(payload)

    assert command.name == "acct_admin"
    assert command.strategy == "trend"
    assert command.benchmark_ticker == "SPY"
    assert command.config.account_kind == " local "
    assert command.config.descriptive_name == "Growth Account"
    assert command.config.option_type == "call"
    assert command.rotation_profile["rotation_enabled"] is True
    assert command.rotation_profile["rotation_interval_days"] == 7


def test_build_account_params_update_command_omits_absent_fields_and_keeps_falsey_values() -> None:
    body = AccountParamsRequest(
        strategy="  mean_reversion  ",
        accountKind=" local ",
        descriptiveName="   ",
        learningEnabled=False,
        optionType="   ",
        rotationActiveIndex=0,
    )

    command = build_account_params_update_command(body)

    assert command.strategy == "mean_reversion"
    assert command.config.account_kind == " local "
    assert command.config_values["descriptive_name"] is None
    assert command.config.learning_enabled is False
    assert command.config.option_type is None
    assert "rotation_last_at" not in command.rotation_profile
    assert command.rotation_profile["rotation_active_index"] == 0
