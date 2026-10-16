#!/usr/bin/env python3
"""Check burn-in stability of daily paper-trading runs and report go-live readiness."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path

from common.runtime_job_status import (
    BROKER_ANOMALY_ACCOUNTS_KEY,
    BURN_IN_STATUS_COMPLETE_SENTINEL,
    DAILY_RUN_STATUS_FAILED,
    DAILY_RUN_STATUS_SUCCESS,
)
from trading.interfaces.runtime.jobs.job_helpers import write_artifact
from trading.interfaces.runtime.jobs.job_runner import JobContext, maintenance_job

JOB_NAME = "check_burn_in_status"
COMPLETE_SENTINEL = BURN_IN_STATUS_COMPLETE_SENTINEL

ACCOUNT_STATUS_KILL_SWITCH = "kill_switch"
# A run that succeeded but recorded a broker API anomaly: not a clean day.
RUN_STATUS_BROKER_ANOMALY = "broker_anomaly"
ACCOUNT_STATUS_BROKER_ANOMALY = "broker_anomaly"
ACCOUNT_STATUS_NOT_TRADED = "not_traded"

# Pattern: daily_paper_trading_YYYYMMDD_HHMMSS.json
_ARTIFACT_RE = re.compile(r"^daily_paper_trading_(\d{8})_(\d{6})\.json$")


def _add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--min-consecutive-days",
        type=int,
        default=10,
        help="Minimum consecutive successful daily runs required (default: 10)",
    )
    parser.add_argument(
        "--max-failure-rate-pct",
        type=float,
        default=0.0,
        help="Maximum acceptable failed-step rate over the window in %%%% (default: 0.0)",
    )
    parser.add_argument(
        "--window-days",
        type=int,
        default=30,
        help="How many calendar days of history to scan for artifacts (default: 30)",
    )
    parser.add_argument(
        "--accounts",
        default="",
        help=(
            "Comma-separated accounts to evaluate individually: a day counts for an account only if the run "
            "succeeded, traded that account, and tripped no kill switch on it. Default: judge whole runs."
        ),
    )


def _name_list(value: object) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


def _load_artifact(artifact_path: Path) -> dict[str, object]:
    """The artifact's JSON object, or ``{}`` when it is unreadable, corrupt, or not an object."""
    try:
        data = json.loads(artifact_path.read_text(encoding="utf-8"))
    except OSError, json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def account_entries(entries: list[dict[str, object]], account: str) -> list[dict[str, object]]:
    """*entries* with each day's status judged for one *account*.

    A successful run counts only if it traded the account (skipped accounts are left out of the
    artifact's ``accounts``) and tripped no kill switch or broker API anomaly on it.
    """
    judged: list[dict[str, object]] = []
    for entry in entries:
        status = entry.get("status")
        if status in (DAILY_RUN_STATUS_SUCCESS, RUN_STATUS_BROKER_ANOMALY):
            if account in _name_list(entry.get(BROKER_ANOMALY_ACCOUNTS_KEY)):
                status = ACCOUNT_STATUS_BROKER_ANOMALY
            elif account in _name_list(entry.get("kill_switch_accounts")):
                status = ACCOUNT_STATUS_KILL_SWITCH
            elif account not in _name_list(entry.get("accounts")):
                status = ACCOUNT_STATUS_NOT_TRADED
            else:
                status = DAILY_RUN_STATUS_SUCCESS
        judged.append({**entry, "status": status})
    return judged


def scan_artifacts(export_dir: Path, window_days: int, today: dt.date) -> list[dict[str, object]]:
    """Scan daily_paper_trading export artifacts within *window_days* of *today*.

    Returns a list of entry dicts sorted chronologically by date, one per
    calendar date. The most-recent artifact for a date sets its status; the accounts that
    traded (from successful artifacts), the kill switches, and the broker API anomalies are
    combined across every artifact of that date, so a catch-up run cannot erase them.
    """
    cutoff = today - dt.timedelta(days=window_days - 1)

    # Group filenames by date prefix; keep only those within the window.
    by_date: dict[str, list[str]] = {}
    if export_dir.is_dir():
        for path in export_dir.iterdir():
            m = _ARTIFACT_RE.match(path.name)
            if not m:
                continue
            date_str = m.group(1)  # YYYYMMDD
            try:
                file_date = dt.date(int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8]))
            except ValueError:
                continue
            if file_date < cutoff or file_date > today:
                continue
            by_date.setdefault(date_str, []).append(path.name)

    entries: list[dict[str, object]] = []
    for date_str, filenames in sorted(by_date.items()):
        # Use lexicographically latest filename (highest HHMMSS = most recent).
        chosen = sorted(filenames)[-1]
        artifacts = [_load_artifact(export_dir / filename) for filename in sorted(filenames)]
        data = artifacts[-1]

        status = data.get("status", DAILY_RUN_STATUS_FAILED)
        anomaly_accounts = sorted(
            {name for item in artifacts for name in _name_list(item.get(BROKER_ANOMALY_ACCOUNTS_KEY))}
        )
        kill_switch_accounts = sorted(
            {name for item in artifacts for name in _name_list(item.get("kill_switch_accounts"))}
        )
        traded_accounts = sorted(
            {
                name
                for item in artifacts
                if item.get("status") == DAILY_RUN_STATUS_SUCCESS
                for name in _name_list(item.get("accounts"))
            }
        )
        if status == DAILY_RUN_STATUS_SUCCESS and anomaly_accounts:
            status = RUN_STATUS_BROKER_ANOMALY
        entry: dict[str, object] = {
            "date": f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}",
            "status": status,
            "artifact_file": chosen,
        }
        if "failed_step" in data:
            entry["failed_step"] = data["failed_step"]
        entry["accounts"] = traded_accounts
        entry["kill_switch_accounts"] = kill_switch_accounts
        entry[BROKER_ANOMALY_ACCOUNTS_KEY] = anomaly_accounts
        entries.append(entry)

    return entries


def evaluate_readiness(
    entries: list[dict[str, object]],
    min_consecutive_days: int,
    max_failure_rate_pct: float,
) -> dict[str, object]:
    """Compute readiness metrics from sorted *entries*."""
    total_runs = len(entries)
    failed_runs = sum(1 for e in entries if e.get("status") != DAILY_RUN_STATUS_SUCCESS)
    failure_rate_pct = (failed_runs / total_runs * 100) if total_runs > 0 else 0.0

    # Count trailing consecutive successful entries.
    consecutive_successes = 0
    for entry in reversed(entries):
        if entry.get("status") == DAILY_RUN_STATUS_SUCCESS:
            consecutive_successes += 1
        else:
            break

    ready_for_live = consecutive_successes >= min_consecutive_days and failure_rate_pct <= max_failure_rate_pct

    return {
        "total_runs_in_window": total_runs,
        "consecutive_successes": consecutive_successes,
        "failed_runs": failed_runs,
        "failure_rate_pct": round(failure_rate_pct, 2),
        "ready_for_live": ready_for_live,
    }


@maintenance_job(
    job_name=JOB_NAME,
    sentinel=COMPLETE_SENTINEL,
    period="day",
    description="Check burn-in stability of daily paper-trading runs.",
    add_arguments=_add_arguments,
)
def main(ctx: JobContext) -> int:
    export_dir = ctx.repo_root / "local" / "exports" / "daily_paper_trading"

    entries = scan_artifacts(export_dir, ctx.args.window_days, ctx.now.date())
    metrics = evaluate_readiness(entries, ctx.args.min_consecutive_days, ctx.args.max_failure_rate_pct)
    account_metrics: dict[str, dict[str, object]] = {}
    for account in (item.strip() for item in ctx.args.accounts.split(",")):
        if account:
            account_metrics[account] = evaluate_readiness(
                account_entries(entries, account), ctx.args.min_consecutive_days, ctx.args.max_failure_rate_pct
            )
    if account_metrics:
        # The headline is the weakest account's: the autonomy monitor reads these keys.
        weakest = min(account_metrics.values(), key=lambda m: int(m["consecutive_successes"]))  # type: ignore[call-overload]
        metrics = {**weakest, "ready_for_live": all(m["ready_for_live"] for m in account_metrics.values())}

    # Written to this job's own long-standing filename, not ctx.artifact_path: the
    # burn-in runbook and the autonomy monitor both look for it, and the runner's
    # day-period name would repeat the date the timestamp already carries.
    artifact_path = ctx.repo_root / "local" / "artifacts" / f"{JOB_NAME}_{ctx.now:%Y%m%d_%H%M%S}.json"
    write_artifact(
        artifact_path,
        {
            "job": JOB_NAME,
            "generated_at": ctx.now.isoformat(),
            "window_days": ctx.args.window_days,
            "min_consecutive_days": ctx.args.min_consecutive_days,
            "max_failure_rate_pct": ctx.args.max_failure_rate_pct,
            **metrics,
            "accounts": account_metrics,
            "entries": entries,
        },
    )

    summary = (
        f"BURN-IN STATUS: consecutive_successes={metrics['consecutive_successes']}"
        f"/{ctx.args.min_consecutive_days} required, "
        f"failure_rate={metrics['failure_rate_pct']}% "
        f"(limit {ctx.args.max_failure_rate_pct}%), "
        f"anomaly_days={sum(1 for entry in entries if entry.get('status') == RUN_STATUS_BROKER_ANOMALY)}, "
        f"ready_for_live={metrics['ready_for_live']}"
    )
    ctx.log(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
