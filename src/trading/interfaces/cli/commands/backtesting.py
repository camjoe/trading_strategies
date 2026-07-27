from __future__ import annotations

import argparse

from trading.services.profiles.source import DEFAULT_TICKERS_FILE


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
    p_backtest.add_argument(
        "--strategy",
        default=None,
        help="Optional strategy override (default: the account's active strategy)",
    )
    p_backtest.add_argument("--run-name", default=None, help="Optional run label")

    p_refresh_stale = sub.add_parser(
        "refresh-stale-backtests",
        help=(
            "Re-run backtests whose evidence is stale or missing, across each account's"
            " rotation candidate strategies (incumbent + challengers)."
        ),
    )
    p_refresh_stale.add_argument("--account", default=None, help="Optional account filter")
    p_refresh_stale.add_argument(
        "--dry-run",
        action="store_true",
        help="List the stale/missing (account, strategy) targets without running backtests",
    )
    p_refresh_stale.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Cap the number of backtests run in one invocation (default: no cap)",
    )
    _add_shared_backtest_args(p_refresh_stale)

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

    p_optimize = sub.add_parser(
        "backtest-optimize",
        help=(
            "Walk-forward parameter optimization for one strategy: grid-search on each"
            " training window, freeze the winner, then report out-of-sample and holdout"
            " evidence against the strategy's default parameters."
        ),
    )
    p_optimize.add_argument("--account", required=True, help="Account name")
    p_optimize.add_argument("--strategy", required=True, help="Strategy to optimize (catalog key or alias)")
    p_optimize.add_argument(
        "--search-space",
        required=True,
        help=(
            "JSON object of parameter -> candidate values, e.g. "
            '\'{"fast_window": [5, 10, 15], "slow_window": [20, 30]}\'. '
            "Keys must be parameters of the strategy."
        ),
    )
    _add_shared_backtest_args(p_optimize)
    p_optimize.add_argument("--train-months", type=int, default=12, help="Training window length in months")
    p_optimize.add_argument("--test-months", type=int, default=1, help="Out-of-sample test window length in months")
    p_optimize.add_argument("--step-months", type=int, default=1, help="Months to roll forward between windows")
    p_optimize.add_argument(
        "--holdout-months",
        type=int,
        default=6,
        help="Untouched final holdout length in months (0 to disable)",
    )
    p_optimize.add_argument(
        "--candidate-budget",
        type=int,
        default=256,
        help="Maximum grid size; a larger Cartesian product is rejected, not truncated",
    )
    p_optimize.add_argument(
        "--warmup-months",
        type=int,
        default=6,
        help="Indicator warm-up history loaded before each window (default: 6); raise for large window params",
    )

    p_optimize_show = sub.add_parser(
        "backtest-optimize-show",
        help="Show a persisted optimization experiment: config, winner params, OOS/holdout evidence, promotion status.",
    )
    p_optimize_show.add_argument("experiment_id", type=int, help="optimization_experiments row id")

    p_optimize_promote = sub.add_parser(
        "backtest-optimize-promote",
        help=(
            "Promote an optimization experiment's winner into a new tradeable strategy variant"
            " (frozen by default) and link it back to the experiment."
        ),
    )
    p_optimize_promote.add_argument("experiment_id", type=int, help="optimization_experiments row id")
    p_optimize_promote.add_argument("--key", required=True, help="Strategy key for the new variant")
    p_optimize_promote.add_argument(
        "--no-freeze",
        action="store_true",
        help="Leave the new variant as an editable draft instead of freezing it (default: freeze)",
    )
    p_optimize_promote.add_argument(
        "--allow-no-edge",
        action="store_true",
        help=(
            "Bypass the promotion quality bar (winner must beat its own default on OOS and holdout"
            " evidence) and promote anyway"
        ),
    )

    p_walk_forward_report = sub.add_parser(
        "backtest-walk-forward-report",
        help="Show persisted walk-forward group details and per-window backtest summaries.",
    )
    p_walk_forward_report.add_argument("--group-id", type=int, default=None, help="Walk-forward group id")
    p_walk_forward_report.add_argument("--account", default=None, help="Account name for latest walk-forward group")
    p_walk_forward_report.add_argument("--strategy", default=None, help="Optional strategy filter with --account")
