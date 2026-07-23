#!/usr/bin/env python3
"""Refresh stale/missing backtests, targeted by the backtest freshness signal.

For each account this enumerates the strategies rotation could promote (each
active book's incumbent plus its challenger schedule) whose newest backtest is
stale or missing, then re-runs a backtest for each — with idempotent retry and
artifact output. Unlike a blind daily refresh it only recomputes what has
actually drifted, and it covers challenger strategies, not just the incumbent.
"""

from __future__ import annotations

import argparse
import re
import time
from pathlib import Path
from typing import Callable

from trading.backtesting.services import find_stale_backtests
from trading.domain.evaluation.backtest_freshness import DEFAULT_BACKTEST_STALE_THRESHOLD_DAYS
from trading.interfaces.runtime.job_status import DAILY_BACKTEST_REFRESH_COMPLETE_SENTINEL
from trading.interfaces.runtime.jobs.job_helpers import (
    CLI_MAIN_MODULE,
    AttemptOutcome,
    run_command,
    run_command_with_retry,
)
from trading.interfaces.runtime.jobs.job_runner import JobContext, daily_account_job
from trading.services.profiles.source import DEFAULT_TICKERS_FILE

JOB_NAME = "daily_backtest_refresh"
COMPLETE_SENTINEL = DAILY_BACKTEST_REFRESH_COMPLETE_SENTINEL

# Explicit opt-in env var so daily reruns remain operator-controlled.
BACKTEST_REFRESH_ENABLED_ENV = "DAILY_BACKTEST_REFRESH_ENABLED"

RUN_ID_PATTERN = re.compile(r"run_id=(?P<run_id>\d+)")


def _add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=3,
        help="Max attempts per backtest command (default: 3)",
    )
    parser.add_argument(
        "--backoff-seconds",
        type=float,
        default=2.0,
        help="Base backoff in seconds between retries (default: 2.0)",
    )
    parser.add_argument(
        "--stale-threshold-days",
        type=int,
        default=DEFAULT_BACKTEST_STALE_THRESHOLD_DAYS,
        help=f"Backtest age (days) above which a refresh is triggered (default: {DEFAULT_BACKTEST_STALE_THRESHOLD_DAYS})",
    )
    parser.add_argument(
        "--tickers-file",
        default=DEFAULT_TICKERS_FILE,
        help=f"Path to ticker universe file (default: {DEFAULT_TICKERS_FILE})",
    )
    parser.add_argument(
        "--universe-history-dir",
        default=None,
        help="Optional folder of monthly universe snapshots named YYYY-MM.txt",
    )
    parser.add_argument("--start", default=None, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", default=None, help="End date YYYY-MM-DD")
    parser.add_argument(
        "--lookback-months",
        type=int,
        default=None,
        help="Alternative to --start: look back N months from end date",
    )
    parser.add_argument("--slippage-bps", type=float, default=5.0, help="Slippage in basis points per trade")
    parser.add_argument("--fee", type=float, default=0.0, help="Fixed fee per trade")
    parser.add_argument(
        "--run-name-prefix",
        default="daily_backtest_refresh",
        help="Prefix for generated backtest run names (default: daily_backtest_refresh)",
    )
    parser.add_argument(
        "--allow-approximate-leaps",
        action="store_true",
        help="Allow approximate LEAPs backtest mode using underlying price proxies",
    )


def _validate(args: argparse.Namespace) -> str | None:
    if int(args.max_attempts) < 1:
        return "--max-attempts must be >= 1"
    if float(args.backoff_seconds) < 0:
        return "--backoff-seconds must be >= 0"
    if int(args.stale_threshold_days) < 0:
        return "--stale-threshold-days must be >= 0"
    return None


def _run_meta(args: argparse.Namespace) -> dict[str, object]:
    return {
        "stale_threshold_days": args.stale_threshold_days,
        "tickers_file": args.tickers_file,
        "universe_history_dir": args.universe_history_dir,
        "start": args.start,
        "end": args.end,
        "lookback_months": args.lookback_months,
        "slippage_bps": args.slippage_bps,
        "fee": args.fee,
        "run_name_prefix": args.run_name_prefix,
        "allow_approximate_leaps": bool(args.allow_approximate_leaps),
        "max_attempts": args.max_attempts,
        "backoff_seconds": args.backoff_seconds,
    }


def build_run_name(*, run_name_prefix: str, day_tag: str, account: str, strategy: str) -> str:
    return f"{run_name_prefix}_{day_tag}_{account}_{strategy}"


def build_backtest_command(
    *,
    account: str,
    strategy: str,
    args: argparse.Namespace,
    day_tag: str,
) -> list[str]:
    command = [
        "-m",
        CLI_MAIN_MODULE,
        "backtest",
        "--account",
        account,
        "--strategy",
        strategy,
        "--tickers-file",
        args.tickers_file,
        "--slippage-bps",
        str(args.slippage_bps),
        "--fee",
        str(args.fee),
        "--run-name",
        build_run_name(run_name_prefix=args.run_name_prefix, day_tag=day_tag, account=account, strategy=strategy),
    ]
    if args.universe_history_dir is not None:
        command.extend(["--universe-history-dir", args.universe_history_dir])
    if args.start is not None:
        command.extend(["--start", args.start])
    if args.end is not None:
        command.extend(["--end", args.end])
    if args.lookback_months is not None:
        command.extend(["--lookback-months", str(args.lookback_months)])
    if bool(args.allow_approximate_leaps):
        command.append("--allow-approximate-leaps")
    return command


def extract_run_id(output: str) -> int | None:
    match = RUN_ID_PATTERN.search(output)
    if match is None:
        return None
    return int(match.group("run_id"))


def run_target_backtest_with_retry(
    *,
    log_path: Path,
    repo_root: Path,
    account: str,
    strategy: str,
    args: argparse.Namespace,
    day_tag: str,
    run_command_fn: Callable[[Path, str, list[str], Path], tuple[int, str]] = run_command,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> dict[str, object]:
    """Run one (account, strategy) backtest with transient-failure retries.

    Success requires both a zero exit code and a parseable ``run_id``; a zero
    exit with no ``run_id`` is a non-retryable ``missing_run_id`` failure. Every
    result payload carries ``run_id`` (``None`` when absent) and ``strategy``.
    """

    def classify(exit_code: int, output: str) -> AttemptOutcome:
        run_id = extract_run_id(output)
        if exit_code == 0 and run_id is not None:
            return AttemptOutcome(succeeded=True, retryable=False, extras={"run_id": run_id, "strategy": strategy})
        if exit_code == 0 and run_id is None:
            return AttemptOutcome(
                succeeded=False,
                retryable=False,
                extras={"run_id": None, "strategy": strategy, "error": "missing_run_id"},
            )
        return AttemptOutcome(succeeded=False, retryable=True, extras={"run_id": run_id, "strategy": strategy})

    return run_command_with_retry(
        log_path=log_path,
        repo_root=repo_root,
        account=account,
        command=build_backtest_command(account=account, strategy=strategy, args=args, day_tag=day_tag),
        label_prefix=f"Backtest refresh [{strategy}]",
        max_attempts=int(args.max_attempts),
        base_backoff_seconds=float(args.backoff_seconds),
        classify=classify,
        result_defaults={"run_id": None, "strategy": strategy},
        run_command_fn=run_command_fn,
        sleep_fn=sleep_fn,
    )


@daily_account_job(
    job_name=JOB_NAME,
    sentinel=COMPLETE_SENTINEL,
    description="Refresh stale or missing backtests across each account's rotation candidate strategies.",
    enabled_env=BACKTEST_REFRESH_ENABLED_ENV,
    disabled_message=(
        "Daily backtest refresh is disabled. Use --enable-run or set DAILY_BACKTEST_REFRESH_ENABLED=1 to execute."
    ),
    run_source_default="daily-backtest-refresh",
    export_subdir="daily_backtest_refresh",
    label="Backtest refresh",
    open_db=True,
    add_arguments=_add_arguments,
    validate=_validate,
    extra_meta=_run_meta,
)
def main(ctx: JobContext, account: str) -> dict[str, object]:
    targets = find_stale_backtests(
        ctx.conn,
        account_name=account,
        threshold_days=int(ctx.args.stale_threshold_days),
    )
    results = [
        run_target_backtest_with_retry(
            log_path=ctx.log_path,
            repo_root=ctx.repo_root,
            account=account,
            strategy=target.strategy_name,
            args=ctx.args,
            day_tag=ctx.tag,
        )
        for target in targets
    ]
    succeeded = all(result.get("status") == "success" for result in results)
    return {
        "account": account,
        "status": "success" if succeeded else "failed",
        "targets": len(targets),
        "results": results,
    }


if __name__ == "__main__":
    raise SystemExit(main())
