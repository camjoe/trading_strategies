"""Command-line argument parsing for the daily paper-trading workflow."""

from __future__ import annotations

import argparse
import os

from common.paths.project_paths import ACCOUNT_TRADE_CAPS_PATH
from common.paths.repo_paths import get_repo_root
from trading.interfaces.runtime.jobs.job_helpers import RUNTIME_ALERT_WEBHOOK_ENV

REPO_ROOT = get_repo_root(__file__)
DEFAULT_TRADE_CAPS_CONFIG = ACCOUNT_TRADE_CAPS_PATH


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the daily paper-trading workflow.")
    parser.add_argument(
        "--accounts",
        default="all",
        help="Comma-separated account names, or 'all' for every account in DB (default: all)",
    )
    parser.add_argument(
        "--primary-accounts",
        default="momentum_5k,meanrev_5k",
        help="Accounts that use the stricter primary trade caps (default: momentum_5k,meanrev_5k)",
    )
    parser.add_argument("--primary-max-trades", type=int, default=5)
    parser.add_argument("--other-max-trades", type=int, default=11)
    parser.add_argument(
        "--account-trade-caps",
        default="",
        help=(
            "Optional per-account maximum overrides in the form "
            "account:max,account:max (example: momentum_5k:5,core_growth_20k:8)"
        ),
    )
    parser.add_argument(
        "--trade-caps-config",
        default=DEFAULT_TRADE_CAPS_CONFIG,
        help=(f"Path to JSON file with default and per-account trade caps (default: {DEFAULT_TRADE_CAPS_CONFIG})"),
    )
    parser.add_argument("--fee", type=float, default=0.0)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument(
        "--run-challenger-shadow-eval",
        action="store_true",
        help="Run challenger shadow evaluation before auto-trading.",
    )
    parser.add_argument(
        "--shadow-eval-rolling-window-days",
        type=int,
        default=None,
        help=(
            "Override the challenger shadow-eval lookback window in days"
            " (default: each book's own configured lookback)."
        ),
    )
    parser.add_argument(
        "--as-of-date",
        default="",
        help=(
            "Override the trading date for this run (YYYY-MM-DD). "
            "Used by replay/backfill tooling to re-run a missed date. "
            "Affects the log/artifact file name prefix."
        ),
    )
    parser.add_argument("--run-source", default="scheduled-daily")
    parser.add_argument(
        "--notify-webhook-url",
        default=os.environ.get(RUNTIME_ALERT_WEBHOOK_ENV, ""),
        help=(f"Optional webhook URL for runtime notifications (default: ${RUNTIME_ALERT_WEBHOOK_ENV} if set)"),
    )
    parser.add_argument(
        "--notify-on-success",
        action="store_true",
        help="Also send a webhook notification when the run completes successfully",
    )
    parser.add_argument(
        "--repo-root",
        default=str(REPO_ROOT),
        help="Repository root path (default: inferred from script location)",
    )
    return parser


def parse_args() -> argparse.Namespace:
    return build_parser().parse_args()
