from __future__ import annotations

import argparse

from trading.services.profile_source import DEFAULT_TICKERS_FILE


def add_backtesting_commands(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p_backtest = sub.add_parser(
        "backtest",
        help="Run a historical backtest for an existing account configuration.",
    )
    p_backtest.add_argument("--account", required=True, help="Account name")
    p_backtest.add_argument(
        "--tickers-file",
        default=DEFAULT_TICKERS_FILE,
        help=f"Path to ticker universe file (default: {DEFAULT_TICKERS_FILE})",
    )
    p_backtest.add_argument(
        "--universe-history-dir",
        default=None,
        help="Optional folder of monthly universe snapshots named YYYY-MM.txt",
    )
    p_backtest.add_argument("--start", default=None, help="Start date YYYY-MM-DD")
    p_backtest.add_argument("--end", default=None, help="End date YYYY-MM-DD")
    p_backtest.add_argument(
        "--lookback-months",
        type=int,
        default=None,
        help="Alternative to --start: look back N months from end date",
    )
    p_backtest.add_argument("--slippage-bps", type=float, default=5.0, help="Slippage in basis points per trade")
    p_backtest.add_argument("--fee", type=float, default=0.0, help="Fixed fee per trade")
    p_backtest.add_argument("--run-name", default=None, help="Optional run label")
    p_backtest.add_argument(
        "--allow-approximate-leaps",
        action="store_true",
        help="Allow approximate LEAPs backtest mode using underlying price proxies",
    )

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
    p_backtest_batch.add_argument(
        "--tickers-file",
        default=DEFAULT_TICKERS_FILE,
        help=f"Path to ticker universe file (default: {DEFAULT_TICKERS_FILE})",
    )
    p_backtest_batch.add_argument(
        "--universe-history-dir",
        default=None,
        help="Optional folder of monthly universe snapshots named YYYY-MM.txt",
    )
    p_backtest_batch.add_argument("--start", default=None, help="Start date YYYY-MM-DD")
    p_backtest_batch.add_argument("--end", default=None, help="End date YYYY-MM-DD")
    p_backtest_batch.add_argument(
        "--lookback-months",
        type=int,
        default=None,
        help="Alternative to --start: look back N months from end date",
    )
    p_backtest_batch.add_argument("--slippage-bps", type=float, default=5.0, help="Slippage in basis points per trade")
    p_backtest_batch.add_argument("--fee", type=float, default=0.0, help="Fixed fee per trade")
    p_backtest_batch.add_argument("--run-name-prefix", default=None, help="Optional prefix for generated run names")
    p_backtest_batch.add_argument(
        "--allow-approximate-leaps",
        action="store_true",
        help="Allow approximate LEAPs backtest mode using underlying price proxies",
    )

    p_walk_forward = sub.add_parser(
        "backtest-walk-forward",
        help="Run rolling monthly walk-forward backtests across a date range.",
    )
    p_walk_forward.add_argument("--account", required=True, help="Account name")
    p_walk_forward.add_argument(
        "--tickers-file",
        default=DEFAULT_TICKERS_FILE,
        help=f"Path to ticker universe file (default: {DEFAULT_TICKERS_FILE})",
    )
    p_walk_forward.add_argument(
        "--universe-history-dir",
        default=None,
        help="Optional folder of monthly universe snapshots named YYYY-MM.txt",
    )
    p_walk_forward.add_argument("--start", default=None, help="Start date YYYY-MM-DD")
    p_walk_forward.add_argument("--end", default=None, help="End date YYYY-MM-DD")
    p_walk_forward.add_argument(
        "--lookback-months",
        type=int,
        default=None,
        help="Alternative to --start: look back N months from end date",
    )
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
    p_walk_forward.add_argument("--slippage-bps", type=float, default=5.0, help="Slippage in basis points per trade")
    p_walk_forward.add_argument("--fee", type=float, default=0.0, help="Fixed fee per trade")
    p_walk_forward.add_argument("--run-name-prefix", default=None, help="Optional prefix for generated run names")
    p_walk_forward.add_argument(
        "--allow-approximate-leaps",
        action="store_true",
        help="Allow approximate LEAPs backtest mode using underlying price proxies",
    )
