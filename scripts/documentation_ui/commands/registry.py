from __future__ import annotations

import argparse
from collections.abc import Callable
from typing import Any

from trading.interfaces.cli.commands.accounts import add_account_commands
from trading.interfaces.cli.commands.advisor import add_advisor_commands
from trading.interfaces.cli.commands.backtesting import add_backtesting_commands
from trading.interfaces.cli.commands.options import add_option_args
from trading.interfaces.cli.commands.reporting import add_reporting_commands
from trading.interfaces.cli.commands.settings import add_settings_commands
from trading.interfaces.cli.commands.strategy_catalog import add_strategy_catalog_commands

COMMANDS_REGISTRY_REL = "apps/paper_trading_web/frontend/src/assets/commands.json"
CLI_INVOCATION = "python -m trading.interfaces.cli.main"

RISK_READ_ONLY = "read-only"
RISK_WRITES_LOCAL = "writes-local"

GROUP_ACCOUNTS = "Accounts"
GROUP_REPORTING = "Reporting"
GROUP_SETTINGS = "Settings"
GROUP_STRATEGY_CATALOG = "Strategy Catalog"
GROUP_BACKTESTING = "Backtesting"
GROUP_ADVISOR = "Advisor"

# Group name -> function that registers that group's subcommands on a subparsers action.
GROUP_ADDERS: dict[str, Callable[[Any], None]] = {
    GROUP_ACCOUNTS: lambda sub: add_account_commands(sub, add_option_args),
    GROUP_REPORTING: add_reporting_commands,
    GROUP_SETTINGS: add_settings_commands,
    GROUP_STRATEGY_CATALOG: add_strategy_catalog_commands,
    GROUP_BACKTESTING: add_backtesting_commands,
    GROUP_ADVISOR: add_advisor_commands,
}

# Every CLI command must be in exactly one of these tables. An unlisted command fails the build.
READ_ONLY_COMMANDS = frozenset(
    {
        "list-accounts",
        "report",
        "promotion-status",
        "promotion-review-history",
        "snapshot-history",
        "portfolio-exposure",
        "portfolio-concentration",
        "parameters",
        "compare-strategies",
        "settings-history",
        "book-rotation-history",
        "backtest-report",
        "backtest-leaderboard",
        "backtest-optimize-show",
        "backtest-bench",
        "advisor-digest",
        "advisor-scorecard",
    }
)
WRITES_LOCAL_COMMANDS = frozenset(
    {
        "init",
        "create-account",
        "set-benchmark",
        "assign-strategy",
        "configure-account",
        "trade",
        "promotion-request-review",
        "promotion-review-action",
        "snapshot",
        "configure-throttle",
        "configure-evaluation",
        "configure-book-rotation-policy",
        "configure-book-rotation",
        "configure-promotion",
        "create-strategy-variant",
        "configure-strategy",
        "freeze-strategy",
        "backtest",
        "backtest-batch",
        "backtest-optimize",
        "backtest-optimize-promote",
        "advisor-record",
        "advisor-score",
    }
)


def _subparsers_action(parser: argparse.ArgumentParser) -> argparse._SubParsersAction[argparse.ArgumentParser]:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action
    raise ValueError("parser has no subcommands")


def _json_safe(value: object) -> object:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return str(value)


def _argument_kind(action: argparse.Action) -> str:
    if isinstance(action, (argparse._StoreTrueAction, argparse._StoreFalseAction)):
        return "flag"
    if isinstance(action, argparse._AppendAction):
        return "repeatable"
    return "value"


def _type_name(action: argparse.Action) -> str:
    if _argument_kind(action) == "flag":
        return "flag"
    return getattr(action.type, "__name__", "str") if action.type is not None else "str"


def _describe_argument(action: argparse.Action) -> dict[str, Any]:
    flags = list(action.option_strings) or [action.dest]
    return {
        "flags": flags,
        "dest": action.dest,
        "kind": _argument_kind(action),
        "type": _type_name(action),
        "required": bool(action.required),
        "default": _json_safe(action.default),
        "choices": _json_safe(list(action.choices)) if action.choices else None,
        "help": " ".join((action.help or "").split()),
    }


def _example_value(argument: dict[str, Any]) -> str:
    if argument["choices"]:
        return str(argument["choices"][0])
    return f"<{argument['dest'].upper()}>"


def _build_example(name: str, arguments: list[dict[str, Any]]) -> str:
    parts = [CLI_INVOCATION, name]
    for argument in arguments:
        if not argument["required"]:
            continue
        flag = argument["flags"][0]
        parts.append(flag if argument["kind"] == "flag" else f"{flag} {_example_value(argument)}")
    return " ".join(parts)


def _risk_for(name: str) -> str:
    in_read_only = name in READ_ONLY_COMMANDS
    in_writes_local = name in WRITES_LOCAL_COMMANDS
    if in_read_only == in_writes_local:
        raise ValueError(f"CLI command {name!r} must be in exactly one risk table in {__name__}")
    return RISK_READ_ONLY if in_read_only else RISK_WRITES_LOCAL


def _group_commands(group: str, adder: Callable[[Any], None]) -> list[dict[str, Any]]:
    parser = argparse.ArgumentParser()
    parser.add_subparsers(dest="command")
    action = _subparsers_action(parser)
    adder(action)
    helps = {choice.dest: choice.help or "" for choice in action._choices_actions}
    rows: list[dict[str, Any]] = []
    for name, command_parser in action.choices.items():
        arguments = [
            _describe_argument(item) for item in command_parser._actions if not isinstance(item, argparse._HelpAction)
        ]
        rows.append(
            {
                "name": name,
                "group": group,
                "risk": _risk_for(name),
                "help": " ".join(helps.get(name, "").split()),
                "example": _build_example(name, arguments),
                "arguments": arguments,
            }
        )
    return rows


def build_command_rows() -> list[dict[str, Any]]:
    """Return one row per CLI subcommand, grouped in registration order."""
    rows: list[dict[str, Any]] = []
    for group, adder in GROUP_ADDERS.items():
        rows.extend(_group_commands(group, adder))
    names = {row["name"] for row in rows}
    stale = (READ_ONLY_COMMANDS | WRITES_LOCAL_COMMANDS) - names
    if stale:
        raise ValueError(f"risk tables list commands that do not exist: {sorted(stale)}")
    return rows


def build_payload() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "cli_invocation": CLI_INVOCATION,
        "groups": list(GROUP_ADDERS),
        "commands": build_command_rows(),
    }
