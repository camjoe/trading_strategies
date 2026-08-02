from __future__ import annotations

from paper_trading_web.backend.account_contract import (
    build_account_params_update_command,
    build_admin_create_account_command,
)
from paper_trading_web.backend.schemas import AccountParamsRequest, AdminCreateAccountRequest
from paper_trading_web.backend.schemas.admin import RotationSettingsPayload


def test_build_admin_create_account_command_maps_account_config_and_rotation_fields() -> None:
    payload = AdminCreateAccountRequest(
        name="  acct_admin  ",
        strategy="  trend  ",
        initialCash=5000.0,
        riskPolicy=" fixed_stop ",
        descriptiveName="  Growth Account  ",
        optionType="  call  ",
        rotation=RotationSettingsPayload(enabled=True, schedule=["trend"], lookbackDays=45),
    )

    command = build_admin_create_account_command(payload)

    assert command.name == "acct_admin"
    assert command.strategy == "trend"
    assert command.benchmark_ticker == "SPY"
    assert command.config.risk_policy == " fixed_stop "
    assert command.config.descriptive_name == "Growth Account"
    assert command.config.option_type == "call"
    assert command.rotation_settings == {"enabled": True, "schedule": ["trend"], "lookback_days": 45}


def test_build_account_params_update_command_omits_absent_fields_and_keeps_falsey_values() -> None:
    body = AccountParamsRequest(
        strategy="  mean_reversion  ",
        riskPolicy=" fixed_stop ",
        descriptiveName="   ",
        learningEnabled=False,
        optionType="   ",
        rotation=RotationSettingsPayload(enabled=False),
    )

    command = build_account_params_update_command(body)

    assert command.strategy == "mean_reversion"
    assert command.config.risk_policy == " fixed_stop "
    assert command.config_values["descriptive_name"] is None
    assert command.config.learning_enabled is False
    assert command.config.option_type is None
    # Absent nested keys are omitted; supplied falsey values survive.
    assert command.rotation_settings == {"enabled": False}


def test_build_account_params_update_command_without_rotation_object() -> None:
    command = build_account_params_update_command(AccountParamsRequest(strategy="trend"))

    assert command.rotation_settings == {}
