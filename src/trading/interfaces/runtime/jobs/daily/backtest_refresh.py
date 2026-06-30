#!/usr/bin/env python3
"""Run daily backtest refreshes with idempotency, retry, and artifact output."""

from __future__ import annotations

import argparse
import re
import time
from pathlib import Path
from typing import Callable

from trading.interfaces.runtime.jobs.job_helpers import (
    AttemptOutcome,
    CLI_MAIN_MODULE,
    run_command,
    run_command_with_retry,
)
from trading.interfaces.runtime.jobs.job_runner import JobContext, account_job
from trading.services.profiles.source import DEFAULT_TICKERS_FILE
from trading.interfaces.runtime.job_status import DAILY_BACKTEST_REFRESH_COMPLETE_SENTINEL

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
        help="Max attempts per account refresh command (default: 3)",
    )
    parser.add_argument(
        "--backoff-seconds",
        type=float,
        default=2.0,
        help="Base backoff in seconds between retries (default: 2.0)",
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
    return None


def _run_meta(args: argparse.Namespace) -> dict[str, object]:
    return {
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


def build_run_name(*, run_name_prefix: str, day_tag: str, account: str) -> str:
    return f"{run_name_prefix}_{day_tag}_{account}"


def build_backtest_command(
    *,
    account: str,
    args: argparse.Namespace,
    day_tag: str,
) -> list[str]:
    command = [
        "-m",
        CLI_MAIN_MODULE,
        "backtest",
        "--account",
        account,
        "--tickers-file",
        args.tickers_file,
        "--slippage-bps",
        str(args.slippage_bps),
        "--fee",
        str(args.fee),
        "--run-name",
        build_run_name(run_name_prefix=args.run_name_prefix, day_tag=day_tag, account=account),
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


def run_backtest_refresh_with_retry(
    *,
    log_path: Path,
    repo_root: Path,
    account: str,
    args: argparse.Namespace,
    day_tag: str,
    run_command_fn: Callable[[Path, str, list[str], Path], tuple[int, str]] = run_command,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> dict[str, object]:
    """Run one account's backtest-refresh command with transient-failure retries.

    Success requires both a zero exit code and a parseable ``run_id``; a zero
    exit with no ``run_id`` is a non-retryable ``missing_run_id`` failure. Every
    result payload carries a ``run_id`` (``None`` when absent).
    """

    def classify(exit_code: int, output: str) -> AttemptOutcome:
        run_id = extract_run_id(output)
        if exit_code == 0 and run_id is not None:
            return AttemptOutcome(succeeded=True, retryable=False, extras={"run_id": run_id})
        if exit_code == 0 and run_id is None:
            return AttemptOutcome(succeeded=False, retryable=False, extras={"run_id": None, "error": "missing_run_id"})
        return AttemptOutcome(succeeded=False, retryable=True, extras={"run_id": run_id})

    return run_command_with_retry(
        log_path=log_path,
        repo_root=repo_root,
        account=account,
        command=build_backtest_command(account=account, args=args, day_tag=day_tag),
        label_prefix="Backtest refresh",
        max_attempts=int(args.max_attempts),
        base_backoff_seconds=float(args.backoff_seconds),
        classify=classify,
        result_defaults={"run_id": None},
        run_command_fn=run_command_fn,
        sleep_fn=sleep_fn,
    )


@account_job(
    job_name=JOB_NAME,
    sentinel=COMPLETE_SENTINEL,
    period="day",
    description="Run daily backtest refreshes for existing accounts.",
    per_account=True,
    enabled_env=BACKTEST_REFRESH_ENABLED_ENV,
    disabled_message=(
        "Daily backtest refresh is disabled. Use --enable-run or set DAILY_BACKTEST_REFRESH_ENABLED=1 to execute."
    ),
    run_source_default="daily-backtest-refresh",
    export_subdir="daily_backtest_refresh",
    label="Backtest refresh",
    open_db=False,
    add_arguments=_add_arguments,
    validate=_validate,
    extra_meta=_run_meta,
)
def main(ctx: JobContext, account: str) -> dict[str, object]:
    return run_backtest_refresh_with_retry(
        log_path=ctx.log_path,
        repo_root=ctx.repo_root,
        account=account,
        args=ctx.args,
        day_tag=ctx.tag,
    )


if __name__ == "__main__":
    raise SystemExit(main())
