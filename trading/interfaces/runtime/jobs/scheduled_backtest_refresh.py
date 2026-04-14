#!/usr/bin/env python3
"""Run scheduled backtest refreshes with idempotency, retry, and artifact output."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Callable

from common.repo_paths import get_repo_root
from trading.interfaces.runtime.jobs.task_runs import latest_log_contains_sentinel, logs_dir_for_repo, run_command, tee_line
from trading.services.accounts_service import load_all_account_names
from trading.services.profile_source import DEFAULT_TICKERS_FILE

REPO_ROOT = get_repo_root(__file__)
LOGS_DIR = logs_dir_for_repo(REPO_ROOT)

# Explicit opt-in env var so scheduled reruns remain operator-controlled.
BACKTEST_REFRESH_ENABLED_ENV = "SCHEDULED_BACKTEST_REFRESH_ENABLED"

# Successful scheduled refresh runs write this sentinel into the newest log.
COMPLETE_SENTINEL = "COMPLETE: Scheduled backtest refresh succeeded."

# Retry only on transient fetch/connectivity errors from market-data dependent backtests.
TRANSIENT_ERROR_TOKENS = (
    "temporarily unavailable",
    "timed out",
    "timeout",
    "connection reset",
    "connection aborted",
    "connection error",
    "temporary failure",
    "try again",
    "rate limit",
    "too many requests",
)

RUN_ID_PATTERN = re.compile(r"run_id=(?P<run_id>\d+)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run scheduled backtest refreshes for existing accounts.")
    parser.add_argument(
        "--accounts",
        default="all",
        help="Comma-separated account names, or 'all' for every account in DB (default: all)",
    )
    parser.add_argument("--force-run", action="store_true", help="Allow duplicate same-day run")
    parser.add_argument("--run-source", default="scheduled-backtest-refresh")
    parser.add_argument(
        "--enable-run",
        action="store_true",
        help="Explicitly enable backtest refresh execution for this invocation",
    )
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
        default="scheduled_refresh",
        help="Prefix for generated backtest run names (default: scheduled_refresh)",
    )
    parser.add_argument(
        "--allow-approximate-leaps",
        action="store_true",
        help="Allow approximate LEAPs backtest mode using underlying price proxies",
    )
    parser.add_argument(
        "--repo-root",
        default=str(REPO_ROOT),
        help="Repository root path (default: inferred from script location)",
    )
    return parser.parse_args()


def is_run_enabled(args: argparse.Namespace) -> bool:
    if bool(args.enable_run):
        return True
    return os.getenv(BACKTEST_REFRESH_ENABLED_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def _day_tag(now: dt.datetime) -> str:
    return now.strftime("%Y%m%d")


def already_completed_today(log_dir: Path, day_tag: str) -> bool:
    return latest_log_contains_sentinel(
        log_dir,
        f"scheduled_backtest_refresh_{day_tag}_*.log",
        COMPLETE_SENTINEL,
    )


def is_transient_error(output: str) -> bool:
    lowered = output.lower()
    return any(token in lowered for token in TRANSIENT_ERROR_TOKENS)


def retry_delay_seconds(base_delay_seconds: float, attempt_number: int) -> float:
    return max(base_delay_seconds, 0.0) * (2 ** (attempt_number - 1))


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
        "trading.interfaces.cli.main",
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
    attempts = max(1, int(args.max_attempts))
    started_at = dt.datetime.now(dt.timezone.utc).astimezone().isoformat()

    for attempt in range(1, attempts + 1):
        label = f"Backtest refresh {account} (attempt {attempt}/{attempts})"
        exit_code, output = run_command_fn(
            log_path,
            label,
            build_backtest_command(account=account, args=args, day_tag=day_tag),
            repo_root,
        )
        run_id = extract_run_id(output)
        if exit_code == 0 and run_id is not None:
            return {
                "account": account,
                "status": "success",
                "attempts": attempt,
                "run_id": run_id,
                "started_at": started_at,
                "finished_at": dt.datetime.now(dt.timezone.utc).astimezone().isoformat(),
                "last_exit_code": exit_code,
            }

        transient = is_transient_error(output)
        failure_payload = {
            "account": account,
            "status": "failed",
            "attempts": attempt,
            "run_id": run_id,
            "started_at": started_at,
            "finished_at": dt.datetime.now(dt.timezone.utc).astimezone().isoformat(),
            "last_exit_code": exit_code,
            "transient": transient,
        }
        if exit_code == 0 and run_id is None:
            failure_payload["error"] = "missing_run_id"
            return failure_payload
        if attempt >= attempts or not transient:
            return failure_payload

        delay_seconds = retry_delay_seconds(float(args.backoff_seconds), attempt)
        tee_line(
            log_path,
            (
                f"[{dt.datetime.now(dt.timezone.utc).astimezone().isoformat()}] RETRY: "
                f"account={account} attempt={attempt} delay_seconds={delay_seconds:.2f}"
            ),
        )
        sleep_fn(delay_seconds)

    return {
        "account": account,
        "status": "failed",
        "attempts": attempts,
        "run_id": None,
        "started_at": started_at,
        "finished_at": dt.datetime.now(dt.timezone.utc).astimezone().isoformat(),
        "last_exit_code": 1,
        "transient": False,
    }


def write_artifact(artifact_path: Path, payload: dict[str, object]) -> None:
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _resolve_accounts(accounts_arg: str, all_accounts: list[str]) -> list[str]:
    if accounts_arg.strip().lower() == "all":
        return all_accounts

    requested = [item.strip() for item in accounts_arg.split(",") if item.strip()]
    known = set(all_accounts)
    missing = [name for name in requested if name not in known]
    if missing:
        raise ValueError(f"Unknown account(s): {', '.join(missing)}")
    return requested


def main() -> int:
    args = parse_args()
    if int(args.max_attempts) < 1:
        print("--max-attempts must be >= 1", file=sys.stderr)
        return 1
    if float(args.backoff_seconds) < 0:
        print("--backoff-seconds must be >= 0", file=sys.stderr)
        return 1

    if not is_run_enabled(args):
        print(
            "Scheduled backtest refresh is disabled. "
            f"Use --enable-run or set {BACKTEST_REFRESH_ENABLED_ENV}=1 to execute.",
            file=sys.stderr,
        )
        return 0

    repo_root = Path(args.repo_root).expanduser().resolve()
    logs_dir = logs_dir_for_repo(repo_root)
    export_dir = repo_root / "local" / "exports" / "scheduled_backtest_refresh"
    logs_dir.mkdir(parents=True, exist_ok=True)
    export_dir.mkdir(parents=True, exist_ok=True)

    now = dt.datetime.now()
    day_tag = _day_tag(now)
    timestamp = now.strftime("%Y%m%d_%H%M%S")
    log_path = logs_dir / f"scheduled_backtest_refresh_{day_tag}_{timestamp}.log"
    artifact_path = export_dir / f"scheduled_backtest_refresh_{timestamp}.json"

    try:
        accounts = _resolve_accounts(args.accounts, load_all_account_names())
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if not accounts:
        print("No accounts specified.", file=sys.stderr)
        return 1

    run_meta = {
        "job": "scheduled_backtest_refresh",
        "run_source": args.run_source,
        "force_run": bool(args.force_run),
        "day_tag": day_tag,
        "accounts": accounts,
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
        "log_path": str(log_path.relative_to(repo_root)),
        "artifact_path": str(artifact_path.relative_to(repo_root)),
        "started_at": dt.datetime.now(dt.timezone.utc).astimezone().isoformat(),
    }
    tee_line(log_path, f"[{dt.datetime.now(dt.timezone.utc).astimezone().isoformat()}] RUN META: {json.dumps(run_meta, sort_keys=True)}")

    if not args.force_run and already_completed_today(logs_dir, day_tag):
        message = "Scheduled backtest refresh already completed today; skipping duplicate run."
        tee_line(log_path, f"[{dt.datetime.now(dt.timezone.utc).astimezone().isoformat()}] SKIP: {message}")
        write_artifact(
            artifact_path,
            {
                **run_meta,
                "status": "skipped",
                "skip_reason": "already-completed-today",
                "results": [],
                "finished_at": dt.datetime.now(dt.timezone.utc).astimezone().isoformat(),
            },
        )
        print(message)
        return 0

    results: list[dict[str, object]] = []
    failed = False
    for account in accounts:
        result = run_backtest_refresh_with_retry(
            log_path=log_path,
            repo_root=repo_root,
            account=account,
            args=args,
            day_tag=day_tag,
        )
        results.append(result)
        if result["status"] != "success":
            failed = True
            tee_line(
                log_path,
                (
                    f"[{dt.datetime.now(dt.timezone.utc).astimezone().isoformat()}] "
                    f"ERROR: Backtest refresh failed for account={account} "
                    f"attempts={result['attempts']} transient={result.get('transient', False)}"
                ),
            )
            break

    if not failed:
        tee_line(log_path, f"[{dt.datetime.now(dt.timezone.utc).astimezone().isoformat()}] {COMPLETE_SENTINEL}")

    write_artifact(
        artifact_path,
        {
            **run_meta,
            "status": "success" if not failed else "failed",
            "results": results,
            "finished_at": dt.datetime.now(dt.timezone.utc).astimezone().isoformat(),
        },
    )
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
