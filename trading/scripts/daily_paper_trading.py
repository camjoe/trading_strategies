#!/usr/bin/env python3
"""Run the daily paper-trading workflow with log + duplicate-run guard."""

from __future__ import annotations

import argparse
import datetime as dt
import subprocess
import sys
from pathlib import Path

COMPLETE_SENTINEL = "COMPLETE: Daily paper trading run succeeded."


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the daily paper-trading workflow.")
    parser.add_argument(
        "--accounts",
        default="momentum_5k,meanrev_5k",
        help="Comma-separated account names (default: momentum_5k,meanrev_5k)",
    )
    parser.add_argument("--min-trades", type=int, default=1)
    parser.add_argument("--max-trades", type=int, default=5)
    parser.add_argument("--fee", type=float, default=0.0)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--force-run", action="store_true", help="Allow duplicate same-day run")
    parser.add_argument("--run-source", default="scheduled-daily")
    return parser.parse_args()


def tee_line(log_path: Path, text: str) -> None:
    print(text)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(text + "\n")


def stream_command(log_path: Path, label: str, args: list[str], cwd: Path) -> None:
    tee_line(log_path, f"[{dt.datetime.now(dt.timezone.utc).astimezone().isoformat()}] START: {label}")
    process = subprocess.Popen(
        [sys.executable, *args],
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
    )
    assert process.stdout is not None
    for line in process.stdout:
        tee_line(log_path, line.rstrip("\n"))
    exit_code = process.wait()
    if exit_code != 0:
        raise RuntimeError(f"Step failed: {label} (exit={exit_code})")
    tee_line(log_path, f"[{dt.datetime.now(dt.timezone.utc).astimezone().isoformat()}] DONE: {label}")


def already_completed_today(log_dir: Path) -> bool:
    today_tag = dt.date.today().strftime("%Y%m%d")
    logs = sorted(log_dir.glob(f"daily_paper_trading_{today_tag}_*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not logs:
        return False
    latest = logs[0]
    try:
        return COMPLETE_SENTINEL in latest.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False


def main() -> int:
    args = parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    log_dir = repo_root / "local" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    if not args.force_run and already_completed_today(log_dir):
        print(f"Daily paper trading already completed today; skipping duplicate run. source={args.run_source}")
        return 0

    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = log_dir / f"daily_paper_trading_{timestamp}.log"

    accounts = [item.strip() for item in args.accounts.split(",") if item.strip()]
    if not accounts:
        print("No accounts specified.", file=sys.stderr)
        return 1

    tee_line(
        log_path,
        f"[{dt.datetime.now(dt.timezone.utc).astimezone().isoformat()}] RUN META: "
        f"source={args.run_source} force={bool(args.force_run)} accounts={','.join(accounts)}",
    )

    try:
        auto_trader_args = [
            "-m",
            "trading.auto_trader",
            "--accounts",
            ",".join(accounts),
            "--min-trades",
            str(args.min_trades),
            "--max-trades",
            str(args.max_trades),
            "--fee",
            str(args.fee),
        ]
        if args.seed is not None:
            auto_trader_args.extend(["--seed", str(args.seed)])

        stream_command(log_path, "Auto Trader", auto_trader_args, repo_root)

        for account in accounts:
            stream_command(
                log_path,
                f"Snapshot {account}",
                ["-m", "trading.paper_trading", "snapshot", "--account", account],
                repo_root,
            )

        stream_command(
            log_path,
            "Compare Strategies",
            ["-m", "trading.paper_trading", "compare-strategies", "--lookback", "10"],
            repo_root,
        )

        tee_line(log_path, f"[{dt.datetime.now(dt.timezone.utc).astimezone().isoformat()}] {COMPLETE_SENTINEL}")
        return 0
    except Exception as exc:
        tee_line(log_path, f"[{dt.datetime.now(dt.timezone.utc).astimezone().isoformat()}] ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
