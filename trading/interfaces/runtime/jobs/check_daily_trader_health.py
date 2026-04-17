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

from common.repo_paths import get_repo_root
from trading.interfaces.runtime.jobs.job_helpers import RUNTIME_ALERT_WEBHOOK_ENV, logs_dir_for_repo
from trading.services.notifications_service import notify_webhook_best_effort
from trading.services.runtime_job_status import DAILY_PAPER_TRADING_COMPLETE_SENTINEL as COMPLETE_SENTINEL

DAILY_PAPER_TRADING_EXECUTION_LOG_PATTERN = "daily_paper_trading_[0-9]*_[0-9]*.log"


class HealthPayload(TypedDict):
    status: str
    message: str
    latest_log: str | None
    latest_log_age_hours: float | None
    sentinel_found: bool


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the latest daily paper trading log is recent and contains a "
            "success sentinel."
        )
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
        "--json",
        action="store_true",
        help="Print machine-readable JSON output",
    )
    parser.add_argument(
        "--notify-webhook-url",
        default=os.environ.get(RUNTIME_ALERT_WEBHOOK_ENV, ""),
        help=(
            "Optional webhook URL for runtime notifications "
            f"(default: ${RUNTIME_ALERT_WEBHOOK_ENV} if set)"
        ),
    )
    parser.add_argument(
        "--notify-on-ok",
        action="store_true",
        help="Also send a webhook notification for successful health checks",
    )
    return parser.parse_args()


def _emit(payload: HealthPayload, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return

    status = str(payload["status"]).upper()
    print(f"[{status}] {payload['message']}")
    if payload.get("latest_log"):
        print(f"latest_log={payload['latest_log']}")
    age = payload.get("latest_log_age_hours")
    if age is not None:
        print(f"latest_log_age_hours={age:.2f}")


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
    notify_webhook_best_effort(
        webhook_url=args.notify_webhook_url,
        event="daily-trader-health",
        status=payload["status"],
        message=payload["message"],
        details={
            "latest_log": payload["latest_log"],
            "latest_log_age_hours": payload["latest_log_age_hours"],
            "sentinel_found": payload["sentinel_found"],
        },
    )


def _finish(args: argparse.Namespace, payload: HealthPayload, exit_code: int) -> int:
    _emit(payload, args.json)
    _maybe_send_notification(args, payload)
    return exit_code


def main() -> int:
    args = parse_args()
    if args.max_age_hours <= 0:
        print("--max-age-hours must be > 0", file=sys.stderr)
        return 2

    repo_root = Path(args.repo_root).expanduser().resolve()
    log_dir = logs_dir_for_repo(repo_root)

    logs = sorted(
        log_dir.glob(DAILY_PAPER_TRADING_EXECUTION_LOG_PATTERN),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
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
    latest_mtime = dt.datetime.fromtimestamp(latest.stat().st_mtime, tz=dt.timezone.utc)
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
            message=(
                f"Latest daily trader log is stale ({age_hours:.2f}h old; "
                f"threshold={args.max_age_hours:.2f}h)"
            ),
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
