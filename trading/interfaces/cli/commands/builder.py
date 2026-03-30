from __future__ import annotations

import argparse

from trading.interfaces.cli.commands.accounts import add_account_commands
from trading.interfaces.cli.commands.backtesting import add_backtesting_commands
from trading.interfaces.cli.commands.options import add_option_args
from trading.interfaces.cli.commands.reporting import add_reporting_commands


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Paper trading accounts per strategy with trade and equity tracking."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    add_account_commands(sub, add_option_args)
    add_reporting_commands(sub)
    add_backtesting_commands(sub)

    return parser
