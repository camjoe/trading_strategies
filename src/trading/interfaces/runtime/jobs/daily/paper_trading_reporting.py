from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from collections.abc import Callable

from infrastructure.database.init import ensure_db
from trading.services.accounts.queries import find_account
from trading.services.sleeves.daily_report import account_daily_report_as_dict, build_account_daily_report

SHADOW_EVAL_EXPORT_DIR = Path("local") / "exports" / "daily_challenger_shadow_eval"


def latest_shadow_eval_summary(repo_root: Path) -> dict[str, object] | None:
    export_dir = repo_root / SHADOW_EVAL_EXPORT_DIR
    artifacts = sorted(
        export_dir.glob("daily_challenger_shadow_eval_*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not artifacts:
        return None
    latest = artifacts[0]
    payload = json.loads(latest.read_text(encoding="utf-8"))
    results = payload.get("results", [])
    if not isinstance(results, list):
        results = []
    sleeve_count = 0
    challenger_count = 0
    for account_result in results:
        if not isinstance(account_result, dict):
            continue
        sleeves = account_result.get("sleeves", [])
        if not isinstance(sleeves, list):
            continue
        sleeve_count += len(sleeves)
        for sleeve in sleeves:
            if not isinstance(sleeve, dict):
                continue
            challenger_count += int(sleeve.get("challenger_count") or 0)
    return {
        "status": payload.get("status"),
        "artifact_path": latest.relative_to(repo_root).as_posix(),
        "account_count": len(results),
        "sleeve_count": sleeve_count,
        "challenger_count": challenger_count,
    }


def build_daily_operator_report(
    accounts: list[str],
    artifact_path: Path,
    repo_root: Path,
    notify_on_success: bool,
) -> dict[str, object]:
    report_date = dt.date.today().isoformat()
    conn = ensure_db()
    account_reports = []
    for account_name in accounts:
        account_row = find_account(conn, account_name)
        if account_row is None:
            continue
        report = build_account_daily_report(
            conn,
            account_id=int(account_row.id),
            account_name=account_name,
            report_date=report_date,
        )
        account_reports.append(account_daily_report_as_dict(report))
    return {
        "artifact_path": artifact_path.relative_to(repo_root).as_posix(),
        "notify_on_success": notify_on_success,
        "report_date": report_date,
        "account_count": len(account_reports),
        "account_reports": account_reports,
    }


def maybe_send_notification(
    *,
    notifier: Callable[..., object],
    webhook_url: str,
    notify_on_success: bool,
    status: str,
    message: str,
    details: dict[str, object],
) -> None:
    if status == "ok" and not notify_on_success:
        return
    notifier(
        webhook_url=webhook_url,
        event="daily-paper-trading",
        status=status,
        message=message,
        details=details,
    )
