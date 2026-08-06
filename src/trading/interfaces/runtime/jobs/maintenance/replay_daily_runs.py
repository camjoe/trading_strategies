#!/usr/bin/env python3
"""Replay missed daily paper-trading runs over a date range.

For each calendar date in [from_date, to_date], checks whether a successful
daily paper-trading run already exists (via the daily job's log-sentinel
helper). Dates that have no successful run are replayed by invoking
daily_paper_trading with --as-of-date.

No --force-run: this filters to dates with no successful run, and the daily job's
duplicate-run guard keys on that same date and sentinel. A date that reaches the
replay invocation is one the guard would pass anyway, so overriding it would only
suppress a disagreement worth seeing.

Usage examples::

    # Dry run — list missing dates without executing
    python -m trading.interfaces.runtime.jobs.maintenance.replay_daily_runs \\
        --from-date 2026-05-01 --to-date 2026-05-06 --dry-run

    # Replay all missing dates in May
    python -m trading.interfaces.runtime.jobs.maintenance.replay_daily_runs \\
        --from-date 2026-05-01 --to-date 2026-05-06

    # Replay a single date
    python -m trading.interfaces.runtime.jobs.maintenance.replay_daily_runs \\
        --from-date 2026-05-03 --to-date 2026-05-03
"""

from __future__ import annotations

import argparse
import datetime as dt
import subprocess
import sys
from pathlib import Path

from common.git import get_repo_root
from trading.interfaces.runtime.jobs.daily.paper_trading import already_completed_today
from trading.interfaces.runtime.jobs.job_helpers import logs_dir_for_repo, ts

REPO_ROOT = get_repo_root(__file__)
DAILY_PAPER_TRADING_MODULE = "trading.interfaces.runtime.jobs.daily.paper_trading"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Replay missed daily paper-trading runs over a date range.",
    )
    parser.add_argument(
        "--from-date",
        required=True,
        help="Start of the replay window (YYYY-MM-DD, inclusive)",
    )
    parser.add_argument(
        "--to-date",
        required=True,
        help="End of the replay window (YYYY-MM-DD, inclusive)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List missing dates without executing any runs",
    )
    parser.add_argument(
        "--accounts",
        default="all",
        help="Comma-separated account names, or 'all' (default: all)",
    )
    parser.add_argument(
        "--run-source",
        default="replay",
        help="run_source tag written into the artifact (default: replay)",
    )
    parser.add_argument(
        "--repo-root",
        default=str(REPO_ROOT),
        help="Repository root path (default: inferred from script location)",
    )
    return parser.parse_args()


def _date_range(from_date: dt.date, to_date: dt.date) -> list[dt.date]:
    days = (to_date - from_date).days
    return [from_date + dt.timedelta(days=i) for i in range(days + 1)]


def _missing_dates(dates: list[dt.date], logs_dir: Path) -> list[dt.date]:
    return [d for d in dates if not already_completed_today(logs_dir, today=d)]


def _replay_date(
    date: dt.date,
    *,
    accounts: str,
    run_source: str,
    repo_root: Path,
) -> int:
    cmd = [
        sys.executable,
        "-m",
        DAILY_PAPER_TRADING_MODULE,
        "--as-of-date",
        date.isoformat(),
        "--accounts",
        accounts,
        "--run-source",
        run_source,
        "--repo-root",
        str(repo_root),
    ]
    print(f"[{ts()}] REPLAY {date}: {' '.join(cmd[2:])}")
    result = subprocess.run(cmd, check=False)
    return result.returncode


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).expanduser().resolve()
    logs_dir = logs_dir_for_repo(repo_root)

    try:
        from_date = dt.date.fromisoformat(args.from_date)
        to_date = dt.date.fromisoformat(args.to_date)
    except ValueError as exc:
        print(f"Invalid date: {exc}", file=sys.stderr)
        return 1

    if from_date > to_date:
        print(f"--from-date {from_date} must be <= --to-date {to_date}", file=sys.stderr)
        return 1

    dates = _date_range(from_date, to_date)
    missing = _missing_dates(dates, logs_dir)

    if not missing:
        print(f"[{ts()}] All {len(dates)} date(s) in range already have successful runs. Nothing to replay.")
        return 0

    print(f"[{ts()}] Found {len(missing)} missing date(s) out of {len(dates)} in range [{from_date} – {to_date}]:")
    for d in missing:
        print(f"  - {d}")

    if args.dry_run:
        print(f"[{ts()}] DRY RUN — no runs executed.")
        return 0

    failed: list[dt.date] = []
    for date in missing:
        code = _replay_date(date, accounts=args.accounts, run_source=args.run_source, repo_root=repo_root)
        if code != 0:
            print(f"[{ts()}] REPLAY {date}: FAILED (exit={code})", file=sys.stderr)
            failed.append(date)
        else:
            print(f"[{ts()}] REPLAY {date}: OK")

    if failed:
        print(f"[{ts()}] {len(failed)} replay(s) failed: {', '.join(str(d) for d in failed)}", file=sys.stderr)
        return 1

    print(f"[{ts()}] All {len(missing)} replay(s) completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
