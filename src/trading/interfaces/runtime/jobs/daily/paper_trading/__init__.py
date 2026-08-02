#!/usr/bin/env python3
"""Run the daily paper-trading workflow with a log + duplicate-run guard.

A second run on a date that already completed is a *second full trading pass*, not
a no-op — step 05 submits a fresh round of orders against a fresh per-run trade
cap. Declining to submit outside US regular equity hours does not cover it: a
scheduled run and an operator re-run an hour later are both inside the window. The
global ``runtime_max_trades_per_day`` throttle would, but it is unset by default.
So the guard is the backstop, and it stays.

The guard keys on the run's *report date* (``--as-of-date`` when given, else
today), which is why replay no longer needs ``--force-run``: ``replay_daily_runs``
only invokes dates with no successful run, so the guard it would have had to
override never fires. ``--force-run`` remains for a deliberate operator re-run,
and is recorded in the run artifact when used.
"""

from __future__ import annotations

import datetime as dt
import sys
import traceback
from pathlib import Path

from common.paths.repo_paths import get_repo_root
from trading.interfaces.runtime.job_status import DAILY_PAPER_TRADING_COMPLETE_SENTINEL
from trading.interfaces.runtime.jobs.daily.paper_trading.arguments import parse_args
from trading.interfaces.runtime.jobs.daily.paper_trading.run_context import (
    RunContextError,
    build_run_context,
)
from trading.interfaces.runtime.jobs.daily.paper_trading.workflow import run_workflow
from trading.interfaces.runtime.jobs.job_helpers import (
    latest_log_contains_sentinel,
    logs_dir_for_repo,
    ts,
)

REPO_ROOT = get_repo_root(__file__)
LOGS_DIR = logs_dir_for_repo(REPO_ROOT)


def _startup_log(message: str, logs_dir: Path = LOGS_DIR) -> None:
    log_path = logs_dir / f"daily_paper_trading_startup_{dt.date.today().strftime('%Y%m%d')}.log"
    timestamp = ts()
    try:
        logs_dir.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"[{timestamp}] {message}\n")
    except OSError:
        pass


try:
    from trading.services.accounts import load_runtime_eligible_account_names
except Exception as exc:
    _startup_log(f"IMPORT ERROR: {exc}")
    _startup_log(traceback.format_exc().rstrip())
    raise


COMPLETE_SENTINEL = DAILY_PAPER_TRADING_COMPLETE_SENTINEL


def already_completed_today(log_dir: Path, *, today: dt.date | None = None) -> bool:
    today_tag = (today or dt.date.today()).strftime("%Y%m%d")
    return latest_log_contains_sentinel(
        log_dir,
        f"daily_paper_trading_{today_tag}_*.log",
        COMPLETE_SENTINEL,
    )


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).expanduser().resolve()
    logs_dir = logs_dir_for_repo(repo_root)

    _startup_log(f"BOOT: script={__file__} cwd={Path.cwd()} python={sys.executable}", logs_dir)
    _startup_log("main() entered", logs_dir)
    logs_dir.mkdir(parents=True, exist_ok=True)

    as_of_date: dt.date | None = None
    if args.as_of_date:
        try:
            as_of_date = dt.date.fromisoformat(args.as_of_date)
        except ValueError:
            print(f"Invalid --as-of-date value: {args.as_of_date!r}. Expected YYYY-MM-DD.", file=sys.stderr)
            return 1

    # Checked before build_run_context, which opens this run's log file — the
    # sentinel glob must only match logs left by earlier runs, never the empty
    # one this run is about to create.
    report_date = as_of_date or dt.date.today()
    if not args.force_run and already_completed_today(logs_dir, today=report_date):
        _startup_log(f"SKIP duplicate run for {report_date} (source={args.run_source})", logs_dir)
        print(
            f"Daily paper trading already completed for {report_date}; skipping duplicate run. "
            f"source={args.run_source}. Use --force-run to override."
        )
        return 0

    all_accounts = load_runtime_eligible_account_names()
    try:
        context = build_run_context(
            args,
            all_accounts=all_accounts,
            as_of_date=as_of_date,
            repo_root=repo_root,
            logs_dir=logs_dir,
        )
    except RunContextError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    _startup_log(f"RUN log_path={context.log_path}", logs_dir)
    return run_workflow(args, context)
