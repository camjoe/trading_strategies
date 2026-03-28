from __future__ import annotations

import argparse

from trading.cli_commands.accounts import add_account_commands
from trading.cli_commands.backtesting import add_backtesting_commands
from trading.cli_commands.options import add_option_args
from trading.cli_commands.reporting import add_reporting_commands


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Paper trading accounts per strategy with trade and equity tracking."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    add_account_commands(sub, add_option_args)
    add_reporting_commands(sub)
    add_backtesting_commands(sub)

    return parser
