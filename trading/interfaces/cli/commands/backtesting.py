from __future__ import annotations

import argparse

from trading.services.profile_source import DEFAULT_TICKERS_FILE


def _add_shared_backtest_args(p: argparse.ArgumentParser) -> None:
    """Add arguments common to backtest, backtest-batch, and backtest-walk-forward."""
    p.add_argument(
        "--tickers-file",
        default=DEFAULT_TICKERS_FILE,
        help=f"Path to ticker universe file (default: {DEFAULT_TICKERS_FILE})",
    )
    p.add_argument(
        "--universe-history-dir",
        default=None,
        help="Optional folder of monthly universe snapshots named YYYY-MM.txt",
    )
    p.add_argument("--start", default=None, help="Start date YYYY-MM-DD")
    p.add_argument("--end", default=None, help="End date YYYY-MM-DD")
    p.add_argument(
        "--lookback-months",
        type=int,
        default=None,
        help="Alternative to --start: look back N months from end date",
    )
    p.add_argument("--slippage-bps", type=float, default=5.0, help="Slippage in basis points per trade")
    p.add_argument("--fee", type=float, default=0.0, help="Fixed fee per trade")
    p.add_argument(
        "--allow-approximate-leaps",
        action="store_true",
        help="Allow approximate LEAPs backtest mode using underlying price proxies",
    )


def add_backtesting_commands(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p_backtest = sub.add_parser(
        "backtest",
        help="Run a historical backtest for an existing account configuration.",
    )
    p_backtest.add_argument("--account", required=True, help="Account name")
    _add_shared_backtest_args(p_backtest)
    p_backtest.add_argument("--run-name", default=None, help="Optional run label")

    p_backtest_report = sub.add_parser(
        "backtest-report",
        help="Show summary metrics for a previous backtest run tied to an account configuration.",
    )
    p_backtest_report.add_argument("--run-id", type=int, required=True, help="Backtest run id")

    p_backtest_leaderboard = sub.add_parser(
        "backtest-leaderboard",
        help="Rank historical account backtest runs by total return.",
    )
    p_backtest_leaderboard.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of runs to return (default: 10)",
    )
    p_backtest_leaderboard.add_argument(
        "--account",
        default=None,
        help="Optional account name filter",
    )
    p_backtest_leaderboard.add_argument(
        "--strategy",
        default=None,
        help="Optional case-insensitive account strategy label filter",
    )

    p_backtest_batch = sub.add_parser(
        "backtest-batch",
        help="Run backtests for multiple accounts with shared date and universe settings.",
    )
    p_backtest_batch.add_argument(
        "--accounts",
        required=True,
        help="Comma-separated account names, e.g. trend_v1,mean_rev_v1",
    )
    _add_shared_backtest_args(p_backtest_batch)
    p_backtest_batch.add_argument("--run-name-prefix", default=None, help="Optional prefix for generated run names")

    p_walk_forward = sub.add_parser(
        "backtest-walk-forward",
        help="Run rolling monthly walk-forward backtests across a date range.",
    )
    p_walk_forward.add_argument("--account", required=True, help="Account name")
    _add_shared_backtest_args(p_walk_forward)
    p_walk_forward.add_argument(
        "--test-months",
        type=int,
        default=1,
        help="Number of months in each walk-forward test window",
    )
    p_walk_forward.add_argument(
        "--step-months",
        type=int,
        default=1,
        help="Months to roll forward between windows",
    )
    p_walk_forward.add_argument("--run-name-prefix", default=None, help="Optional prefix for generated run names")

    p_walk_forward_report = sub.add_parser(
        "backtest-walk-forward-report",
        help="Show persisted walk-forward group details and per-window backtest summaries.",
    )
    p_walk_forward_report.add_argument("--group-id", type=int, default=None, help="Walk-forward group id")
    p_walk_forward_report.add_argument("--account", default=None, help="Account name for latest walk-forward group")
    p_walk_forward_report.add_argument("--strategy", default=None, help="Optional strategy filter with --account")
