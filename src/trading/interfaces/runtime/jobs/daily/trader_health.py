#!/usr/bin/env python3
"""Check whether daily paper trading has run recently and completed successfully."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import TypedDict

from common.files import modified_at_utc, sorted_by_mtime_desc
from common.git import get_repo_root
from common.runtime_job_status import DAILY_PAPER_TRADING_COMPLETE_SENTINEL as COMPLETE_SENTINEL
from common.time import utc_today
from infrastructure.database.connection import db_session
from trading.interfaces.runtime.jobs.job_helpers import (
    RUNTIME_ALERT_WEBHOOK_ENV,
    logs_dir_for_repo,
    resolve_email_config_from_env,
)
from trading.interfaces.runtime.notifications import notify_runtime_event
from trading.services.operations.account_freshness import (
    DEFAULT_FAIL_AFTER_WEEKDAYS,
    DEFAULT_WARN_AFTER_WEEKDAYS,
    AccountFreshness,
    FreshnessReport,
    check_account_freshness,
)

DAILY_PAPER_TRADING_EXECUTION_LOG_PATTERN = "daily_paper_trading_[0-9]*_[0-9]*.log"


class HealthPayload(TypedDict):
    status: str
    message: str
    latest_log: str | None
    latest_log_age_hours: float | None
    sentinel_found: bool


class FreshnessPayload(TypedDict):
    status: str
    message: str
    accounts: list[str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=("Validate the latest daily paper trading log is recent and contains a success sentinel.")
    )
    parser.add_argument(
        "--repo-root",
        default=str(get_repo_root(__file__)),
        help="Repository root path (default: inferred from script location)",
    )
    parser.add_argument(
        "--max-age-hours",
        type=float,
        default=24.0,
        help="Maximum allowed age of the latest run log in hours (default: 24)",
    )
    parser.add_argument(
        "--warn-after-weekdays",
        type=int,
        default=DEFAULT_WARN_AFTER_WEEKDAYS,
        help=f"Weekdays without an equity snapshot before an account is a warning (default: {DEFAULT_WARN_AFTER_WEEKDAYS})",
    )
    parser.add_argument(
        "--fail-after-weekdays",
        type=int,
        default=DEFAULT_FAIL_AFTER_WEEKDAYS,
        help=f"Weekdays without an equity snapshot before an account is a failure (default: {DEFAULT_FAIL_AFTER_WEEKDAYS})",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON output",
    )
    parser.add_argument(
        "--notify-webhook-url",
        default=os.environ.get(RUNTIME_ALERT_WEBHOOK_ENV, ""),
        help=(f"Optional webhook URL for runtime notifications (default: ${RUNTIME_ALERT_WEBHOOK_ENV} if set)"),
    )
    parser.add_argument(
        "--notify-on-ok",
        action="store_true",
        help="Also send a webhook notification for successful health checks",
    )
    return parser.parse_args()


def _emit(payload: HealthPayload, as_json: bool, freshness: FreshnessPayload | None = None) -> None:
    if as_json:
        print(json.dumps({**payload, "freshness": freshness}, indent=2, sort_keys=True))
        return

    status = str(payload["status"]).upper()
    print(f"[{status}] {payload['message']}")
    if payload.get("latest_log"):
        print(f"latest_log={payload['latest_log']}")
    age = payload.get("latest_log_age_hours")
    if age is not None:
        print(f"latest_log_age_hours={age:.2f}")
    if freshness is not None:
        print(f"[{freshness['status'].upper()}] {freshness['message']}")


def _make_payload(
    *,
    status: str,
    message: str,
    latest_log: str | None,
    latest_log_age_hours: float | None,
    sentinel_found: bool,
) -> HealthPayload:
    return {
        "status": status,
        "message": message,
        "latest_log": latest_log,
        "latest_log_age_hours": latest_log_age_hours,
        "sentinel_found": sentinel_found,
    }


def _maybe_send_notification(args: argparse.Namespace, payload: HealthPayload) -> None:
    if payload["status"] == "ok" and not args.notify_on_ok:
        return
    notify_runtime_event(
        webhook_url=args.notify_webhook_url,
        email_config=resolve_email_config_from_env(),
        event="daily-trader-health",
        status=payload["status"],
        message=payload["message"],
        details={
            "latest_log": payload["latest_log"],
            "latest_log_age_hours": payload["latest_log_age_hours"],
            "sentinel_found": payload["sentinel_found"],
        },
    )


def _describe(entry: AccountFreshness) -> str:
    if entry.last_snapshot_date is None:
        return f"{entry.account_name} (never snapshotted)"
    return f"{entry.account_name} (last snapshot {entry.last_snapshot_date}, {entry.weekdays_stale} weekdays ago)"


def _freshness_payload(report: FreshnessReport) -> FreshnessPayload:
    stale = [*report.fail, *report.never, *report.warn]
    if not stale:
        return {"status": "ok", "message": "Every account has a recent equity snapshot", "accounts": []}
    status = "fail" if report.fail else "warn"
    accounts = [_describe(entry) for entry in stale]
    return {
        "status": status,
        "message": f"{len(accounts)} account(s) without a recent equity snapshot: {'; '.join(accounts)}",
        "accounts": accounts,
    }


def _check_freshness(args: argparse.Namespace) -> FreshnessPayload:
    try:
        with db_session() as conn:
            report = check_account_freshness(
                conn,
                as_of=utc_today(),
                warn_after=args.warn_after_weekdays,
                fail_after=args.fail_after_weekdays,
            )
    except Exception as exc:  # the check could not run: report it, never read it as fresh
        return {
            "status": "fail",
            "message": f"Account freshness check could not run: {type(exc).__name__}: {exc}",
            "accounts": [],
        }
    return _freshness_payload(report)


def _maybe_send_freshness_notification(args: argparse.Namespace, freshness: FreshnessPayload) -> None:
    if freshness["status"] == "ok" and not args.notify_on_ok:
        return
    notify_runtime_event(
        webhook_url=args.notify_webhook_url,
        email_config=resolve_email_config_from_env(),
        event="account-freshness",
        status=freshness["status"],
        message=freshness["message"],
        details={"accounts": freshness["accounts"]},
    )


def _finish(args: argparse.Namespace, payload: HealthPayload, exit_code: int) -> int:
    freshness = _check_freshness(args)
    _emit(payload, args.json, freshness)
    _maybe_send_notification(args, payload)
    _maybe_send_freshness_notification(args, freshness)
    return 1 if freshness["status"] == "fail" else exit_code


def main() -> int:
    args = parse_args()
    if args.max_age_hours <= 0:
        print("--max-age-hours must be > 0", file=sys.stderr)
        return 2
    if not 1 <= args.warn_after_weekdays <= args.fail_after_weekdays:
        print("--warn-after-weekdays and --fail-after-weekdays must satisfy 1 <= warn <= fail", file=sys.stderr)
        return 2

    repo_root = Path(args.repo_root).expanduser().resolve()
    log_dir = logs_dir_for_repo(repo_root)

    logs = sorted_by_mtime_desc(log_dir.glob(DAILY_PAPER_TRADING_EXECUTION_LOG_PATTERN))
    if not logs:
        payload = _make_payload(
            status="fail",
            message=f"No daily trader logs found in {log_dir}",
            latest_log=None,
            latest_log_age_hours=None,
            sentinel_found=False,
        )
        return _finish(args, payload, 1)

    latest = logs[0]
    now = dt.datetime.now(dt.timezone.utc)
    latest_mtime = modified_at_utc(latest)
    age_hours = (now - latest_mtime).total_seconds() / 3600.0

    try:
        text = latest.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        payload = _make_payload(
            status="fail",
            message=f"Unable to read latest log: {exc}",
            latest_log=str(latest),
            latest_log_age_hours=age_hours,
            sentinel_found=False,
        )
        return _finish(args, payload, 1)

    sentinel_found = COMPLETE_SENTINEL in text

    if age_hours > args.max_age_hours:
        payload = _make_payload(
            status="fail",
            message=(f"Latest daily trader log is stale ({age_hours:.2f}h old; threshold={args.max_age_hours:.2f}h)"),
            latest_log=str(latest),
            latest_log_age_hours=age_hours,
            sentinel_found=sentinel_found,
        )
        return _finish(args, payload, 1)

    if not sentinel_found:
        payload = _make_payload(
            status="fail",
            message="Latest daily trader log is missing success sentinel",
            latest_log=str(latest),
            latest_log_age_hours=age_hours,
            sentinel_found=False,
        )
        return _finish(args, payload, 1)

    payload = _make_payload(
        status="ok",
        message="Daily trader health check passed",
        latest_log=str(latest),
        latest_log_age_hours=age_hours,
        sentinel_found=True,
    )
    return _finish(args, payload, 0)


if __name__ == "__main__":
    raise SystemExit(main())
