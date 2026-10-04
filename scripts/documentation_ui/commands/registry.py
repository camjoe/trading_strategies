from __future__ import annotations

import argparse
from collections.abc import Callable
from typing import Any

from scripts.documentation_ui.commands.entrypoints import build_entrypoint_rows
from scripts.documentation_ui.commands.introspect import (
    KIND_CLI,
    RISK_READ_ONLY,
    RISK_WRITES_LOCAL,
    describe_arguments,
    make_row,
    subcommand_helps,
    subparsers_action,
)
from trading.interfaces.cli.commands.accounts import add_account_commands
from trading.interfaces.cli.commands.advisor import add_advisor_commands
from trading.interfaces.cli.commands.backtesting import add_backtesting_commands
from trading.interfaces.cli.commands.options import add_option_args
from trading.interfaces.cli.commands.reporting import add_reporting_commands
from trading.interfaces.cli.commands.settings import add_settings_commands
from trading.interfaces.cli.commands.strategy_catalog import add_strategy_catalog_commands

COMMANDS_REGISTRY_REL = "apps/paper_trading_web/frontend/src/assets/commands.json"
CLI_MODULE = "trading.interfaces.cli.main"
CLI_INVOCATION = f"python -m {CLI_MODULE}"

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
# Read-only commands the web UI must not run: a bench run takes minutes and fetches market data.
NOT_RUNNABLE_FROM_UI = frozenset({"backtest-bench"})
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


def _risk_for(name: str) -> str:
    in_read_only = name in READ_ONLY_COMMANDS
    in_writes_local = name in WRITES_LOCAL_COMMANDS
    if in_read_only == in_writes_local:
        raise ValueError(f"CLI command {name!r} must be in exactly one risk table in {__name__}")
    return RISK_READ_ONLY if in_read_only else RISK_WRITES_LOCAL


def _group_commands(group: str, adder: Callable[[Any], None]) -> list[dict[str, Any]]:
    parser = argparse.ArgumentParser()
    parser.add_subparsers(dest="command")
    action = subparsers_action(parser)
    if action is None:
        raise ValueError("parser has no subcommands")
    adder(action)
    helps = subcommand_helps(action)
    return [
        make_row(
            name=name,
            kind=KIND_CLI,
            group=group,
            risk=_risk_for(name),
            help_text=helps.get(name, ""),
            invocation=CLI_INVOCATION,
            argv=["-m", CLI_MODULE],
            subcommand=name,
            arguments=describe_arguments(command_parser),
            runnable=name in READ_ONLY_COMMANDS and name not in NOT_RUNNABLE_FROM_UI,
        )
        for name, command_parser in action.choices.items()
    ]


def build_cli_rows() -> list[dict[str, Any]]:
    """Return one row per CLI subcommand, grouped in registration order."""
    rows: list[dict[str, Any]] = []
    for group, adder in GROUP_ADDERS.items():
        rows.extend(_group_commands(group, adder))
    names = {row["name"] for row in rows}
    stale = (READ_ONLY_COMMANDS | WRITES_LOCAL_COMMANDS | NOT_RUNNABLE_FROM_UI) - names
    if stale:
        raise ValueError(f"risk tables list commands that do not exist: {sorted(stale)}")
    unclassified = NOT_RUNNABLE_FROM_UI - READ_ONLY_COMMANDS
    if unclassified:
        raise ValueError(f"NOT_RUNNABLE_FROM_UI lists commands that are not read-only: {sorted(unclassified)}")
    return rows


def build_payload() -> dict[str, Any]:
    rows = [*build_cli_rows(), *build_entrypoint_rows()]
    names = [row["name"] for row in rows]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise ValueError(f"duplicate catalog names: {duplicates}")
    groups: list[dict[str, str]] = []
    for row in rows:
        entry = {"name": row["group"], "kind": row["kind"]}
        if entry not in groups:
            groups.append(entry)
    return {
        "schema_version": 2,
        "cli_invocation": CLI_INVOCATION,
        "groups": groups,
        "commands": rows,
    }
