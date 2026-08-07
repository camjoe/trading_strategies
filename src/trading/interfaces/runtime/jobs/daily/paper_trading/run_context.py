"""Assemble the resolved run context for the daily paper-trading workflow.

``build_run_context`` turns parsed arguments plus the eligible-account list
into the paths, resolved accounts, trade caps, and run metadata the workflow
consumes. Operator-facing resolution failures raise ``RunContextError`` with a
ready-to-print message; the caller prints it to stderr and exits non-zero.
"""

from __future__ import annotations

import argparse
import datetime as dt
from dataclasses import dataclass
from pathlib import Path

from trading.interfaces.runtime.jobs.daily.paper_trading.caps import (
    parse_account_trade_caps,
    resolve_trade_caps,
)
from trading.interfaces.runtime.jobs.daily.paper_trading.validation import (
    validate_account_trade_cap_overrides,
    validate_trade_count_args,
)
from trading.interfaces.runtime.jobs.job_helpers import resolve_accounts, tee_line, ts


class RunContextError(Exception):
    """Operator-facing error raised while assembling the run context."""


@dataclass(frozen=True)
class DailyRunContext:
    repo_root: Path
    log_path: Path
    artifact_path: Path
    accounts: list[str]
    account_trade_caps: dict[str, int]
    caps_summary: str
    run_meta: dict[str, object]
    # The trading date this run reports on (YYYY-MM-DD). Every reporting step
    # reads it rather than calling `date.today()` itself, so a replay driven by
    # --as-of-date reports the replayed date's rows instead of today's, and the
    # artifact cannot end up carrying two different dates.
    report_date: str


def build_run_context(
    args: argparse.Namespace,
    *,
    all_accounts: list[str],
    as_of_date: dt.date | None,
    repo_root: Path,
    logs_dir: Path,
) -> DailyRunContext:
    date_prefix = as_of_date.strftime("%Y%m%d") if as_of_date else dt.datetime.now().strftime("%Y%m%d")
    time_suffix = dt.datetime.now().strftime("%H%M%S")
    timestamp = f"{date_prefix}_{time_suffix}"
    log_path = logs_dir / f"daily_paper_trading_{timestamp}.log"
    artifact_path = repo_root / "local" / "exports" / "daily_paper_trading" / f"daily_paper_trading_{timestamp}.json"

    try:
        accounts = resolve_accounts(args.accounts, all_accounts)
    except ValueError as exc:
        raise RunContextError(str(exc)) from exc
    if not accounts:
        raise RunContextError("No accounts specified.")

    trade_count_error = validate_trade_count_args(args)
    if trade_count_error:
        raise RunContextError(trade_count_error)

    primary_accounts = {item.strip() for item in args.primary_accounts.split(",") if item.strip()}

    try:
        account_trade_cap_overrides = parse_account_trade_caps(args.account_trade_caps)
    except ValueError as exc:
        raise RunContextError(str(exc)) from exc

    override_error = validate_account_trade_cap_overrides(account_trade_cap_overrides, all_accounts)
    if override_error:
        raise RunContextError(override_error)

    account_trade_caps = resolve_trade_caps(
        accounts,
        primary_accounts,
        args.primary_max_trades,
        args.other_max_trades,
        account_trade_cap_overrides,
    )
    caps_summary = ",".join(f"{name}:{max_trades}" for name, max_trades in account_trade_caps.items())

    tee_line(
        log_path,
        f"[{ts()}] RUN META: source={args.run_source} force={bool(args.force_run)} "
        f"accounts={','.join(accounts)} caps={caps_summary}",
    )
    report_date = (as_of_date or dt.date.today()).isoformat()
    run_meta: dict[str, object] = {
        "job": "daily_paper_trading",
        "run_source": args.run_source,
        # True only when an operator overrode the duplicate-run guard, so a run
        # that traded a date twice says so in its own artifact.
        "force_run": bool(args.force_run),
        "as_of_date": str(as_of_date) if as_of_date else None,
        "report_date": report_date,
        "accounts": accounts,
        "account_count": len(accounts),
        "caps_summary": caps_summary,
        "log_path": str(log_path.relative_to(repo_root)),
        "artifact_path": str(artifact_path.relative_to(repo_root)),
        "started_at": ts(),
    }

    return DailyRunContext(
        repo_root=repo_root,
        log_path=log_path,
        artifact_path=artifact_path,
        accounts=accounts,
        account_trade_caps=account_trade_caps,
        caps_summary=caps_summary,
        run_meta=run_meta,
        report_date=report_date,
    )
