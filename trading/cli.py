import argparse

from trading.cli_commands.accounts import add_account_commands
from trading.cli_commands.backtesting import add_backtesting_commands
from trading.cli_commands.reporting import add_reporting_commands


def _add_option_args(p: argparse.ArgumentParser, *, configure_mode: bool = False) -> None:
    """Add shared account option/risk arguments to a sub-parser."""
    p.add_argument("--display-name", default=None, help="Human-friendly account name")
    p.add_argument("--goal-min-return-pct", type=float, default=None, help="Goal minimum return percent")
    p.add_argument("--goal-max-return-pct", type=float, default=None, help="Goal maximum return percent")
    p.add_argument(
        "--goal-period",
        default=None if configure_mode else "monthly",
        help="Goal time period label, e.g. weekly, monthly, quarterly",
    )
    p.add_argument(
        "--learning-enabled",
        action="store_true",
        help="Turn on learning mode for this account" if configure_mode else "Enable learning mode for this account",
    )
    if configure_mode:
        p.add_argument(
            "--learning-disabled",
            action="store_true",
            help="Turn off learning mode for this account",
        )
    p.add_argument(
        "--risk-policy",
        default=None if configure_mode else "none",
        choices=["none", "fixed_stop", "take_profit", "stop_and_target"],
        help="Risk management policy",
    )
    p.add_argument("--stop-loss-pct", type=float, default=None, help="Stop-loss percent")
    p.add_argument("--take-profit-pct", type=float, default=None, help="Take-profit percent")
    p.add_argument(
        "--instrument-mode",
        default=None if configure_mode else "equity",
        choices=["equity", "leaps"],
        help="Execution style: equity shares or LEAPs-style simulation",
    )
    p.add_argument(
        "--option-strike-offset-pct",
        type=float,
        default=None,
        help="Option strike offset percent vs underlying (for LEAPs simulation)",
    )
    p.add_argument("--option-min-dte", type=int, default=None, help="Minimum days-to-expiration")
    p.add_argument("--option-max-dte", type=int, default=None, help="Maximum days-to-expiration")
    p.add_argument(
        "--option-type",
        default=None,
        choices=["call", "put", "both"],
        help="Preferred option type for options-style trading",
    )
    p.add_argument("--target-delta-min", type=float, default=None, help="Minimum target option delta (0-1)")
    p.add_argument("--target-delta-max", type=float, default=None, help="Maximum target option delta (0-1)")
    p.add_argument("--max-premium-per-trade", type=float, default=None, help="Max option premium budget per trade")
    p.add_argument("--max-contracts-per-trade", type=int, default=None, help="Maximum option contracts per trade")
    p.add_argument("--iv-rank-min", type=float, default=None, help="Minimum IV rank threshold (0-100)")
    p.add_argument("--iv-rank-max", type=float, default=None, help="Maximum IV rank threshold (0-100)")
    p.add_argument("--roll-dte-threshold", type=int, default=None, help="Roll position when DTE <= threshold")
    p.add_argument("--profit-take-pct", type=float, default=None, help="Profit target percent")
    p.add_argument("--max-loss-pct", type=float, default=None, help="Maximum tolerated loss percent")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Paper trading accounts per strategy with trade and equity tracking."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    add_account_commands(sub, _add_option_args)
    add_reporting_commands(sub)
    add_backtesting_commands(sub)

    return parser
