from __future__ import annotations

import pytest

from trading.interfaces.cli.commands import build_parser


def test_create_account_defaults_and_required_fields() -> None:
    parser = build_parser()

    args = parser.parse_args(
        [
            "create-account",
            "--name",
            "acct1",
            "--strategy",
            "trend",
            "--initial-cash",
            "10000",
        ]
    )

    assert args.command == "create-account"
    assert args.benchmark == "SPY"
    assert args.goal_period == "monthly"
    assert args.learning_enabled is False
    assert args.risk_policy == "none"
    assert args.instrument_mode == "equity"
    assert args.option_type is None


def test_configure_account_defaults_do_not_force_values() -> None:
    parser = build_parser()

    args = parser.parse_args(["configure-account", "--account", "acct1"])

    assert args.command == "configure-account"
    assert args.goal_period is None
    assert args.risk_policy is None
    assert args.instrument_mode is None
    assert args.learning_enabled is False
    assert args.learning_disabled is False


@pytest.mark.parametrize("option_type", ["call", "put", "both"])
def test_option_type_choices_parse_for_create_account(option_type: str) -> None:
    parser = build_parser()

    args = parser.parse_args(
        [
            "create-account",
            "--name",
            "acct1",
            "--strategy",
            "trend",
            "--initial-cash",
            "5000",
            "--option-type",
            option_type,
        ]
    )

    assert args.option_type == option_type


@pytest.mark.parametrize(
    "instrument_mode,risk_policy",
    [
        ("equity", "none"),
        ("leaps", "fixed_stop"),
        ("equity", "take_profit"),
        ("leaps", "stop_and_target"),
    ],
)
def test_enum_choices_parse_for_configure_account(instrument_mode: str, risk_policy: str) -> None:
    parser = build_parser()

    args = parser.parse_args(
        [
            "configure-account",
            "--account",
            "acct1",
            "--instrument-mode",
            instrument_mode,
            "--risk-policy",
            risk_policy,
        ]
    )

    assert args.instrument_mode == instrument_mode
    assert args.risk_policy == risk_policy


def test_apply_account_profiles_defaults() -> None:
    parser = build_parser()

    args = parser.parse_args(["apply-account-profiles"])

    assert args.file == "trading/config/account_profiles/default.json"
    assert args.no_create_missing is False


def test_apply_account_preset_requires_choice() -> None:
    parser = build_parser()

    args = parser.parse_args(["apply-account-preset", "--preset", "aggressive"])

    assert args.preset == "aggressive"
    assert args.no_create_missing is False