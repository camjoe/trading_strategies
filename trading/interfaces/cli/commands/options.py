from __future__ import annotations

import argparse

DISPLAY_NAME_HELP = "Display name shown in operator summaries and reports"
EXPLORATION_MODE_HELP = "heuristic exploration mode for this account"
LEAPS_PROFIT_TAKE_HELP = "LEAPs/options profit-take percent"
LEAPS_MAX_LOSS_HELP = "LEAPs/options maximum tolerated loss percent"


def add_option_args(p: argparse.ArgumentParser, *, configure_mode: bool = False) -> None:
    """Add shared account option/risk arguments to a sub-parser."""
    p.add_argument("--display-name", default=None, help=DISPLAY_NAME_HELP)
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
        help=(
            f"Turn on {EXPLORATION_MODE_HELP}"
            if configure_mode
            else f"Enable {EXPLORATION_MODE_HELP}"
        ),
    )
    if configure_mode:
        p.add_argument(
            "--learning-disabled",
            action="store_true",
            help=f"Turn off {EXPLORATION_MODE_HELP}",
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
    p.add_argument("--profit-take-pct", type=float, default=None, help=LEAPS_PROFIT_TAKE_HELP)
    p.add_argument("--max-loss-pct", type=float, default=None, help=LEAPS_MAX_LOSS_HELP)
