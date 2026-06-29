from __future__ import annotations

import argparse

from trading.interfaces.cli.commands.options import add_option_args


def test_add_option_args_defaults_for_create_mode() -> None:
    parser = argparse.ArgumentParser()
    add_option_args(parser, configure_mode=False)

    args = parser.parse_args([])

    assert args.goal_period == "monthly"
    assert args.risk_policy == "none"
    assert args.instrument_mode == "equity"
    assert args.learning_enabled is False
    assert not hasattr(args, "learning_disabled")


def test_add_option_args_defaults_for_configure_mode() -> None:
    parser = argparse.ArgumentParser()
    add_option_args(parser, configure_mode=True)

    args = parser.parse_args([])

    assert args.goal_period is None
    assert args.risk_policy is None
    assert args.instrument_mode is None
    assert args.learning_enabled is False
    assert args.learning_disabled is False


def test_add_option_args_help_uses_operator_facing_labels() -> None:
    parser = argparse.ArgumentParser()
    add_option_args(parser, configure_mode=True)

    assert "Display name" in parser._option_string_actions["--display-name"].help
    assert "heuristic exploration mode" in parser._option_string_actions["--learning-enabled"].help
    assert "heuristic exploration mode" in parser._option_string_actions["--learning-disabled"].help
    assert "LEAPs/options" in parser._option_string_actions["--profit-take-pct"].help
    assert "LEAPs/options" in parser._option_string_actions["--max-loss-pct"].help
