#!/usr/bin/env python3
"""M1 monthly governance job — risk budget rebaseline report for operator review."""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

from common.paths.repo_paths import get_repo_root
from trading.database.db_init import ensure_db
from trading.interfaces.runtime.jobs.job_helpers import (
    already_completed_for_period,
    logs_dir_for_repo,
    month_tag,
    resolve_accounts,
    skip_if_already_completed_for_period,
    tee_line,
    ts,
    write_artifact,
)
from trading.interfaces.runtime.job_status import MONTHLY_GOVERNANCE_M1_RISK_REBASELINE_COMPLETE_SENTINEL
from trading.services.risk_snapshots import fetch_latest_risk_snapshot
from trading.services.accounts.queries import find_account
from trading.services.accounts import load_runtime_eligible_account_names

REPO_ROOT = get_repo_root(__file__)
LOGS_DIR = logs_dir_for_repo(REPO_ROOT)

COMPLETE_SENTINEL = MONTHLY_GOVERNANCE_M1_RISK_REBASELINE_COMPLETE_SENTINEL

JOB_NAME = "monthly_governance_m1_risk_rebaseline"


def already_completed_this_month(log_dir: Path, tag: str) -> bool:
    return already_completed_for_period(
        log_dir=log_dir,
        job_name=JOB_NAME,
        period_tag=tag,
        sentinel=COMPLETE_SENTINEL,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="M1 monthly governance: risk budget rebaseline report per account.",
    )
    parser.add_argument(
        "--accounts",
        default="all",
        help="Comma-separated account names, or 'all' (default: all)",
    )
    parser.add_argument("--force-run", action="store_true", help="Allow duplicate same-month run")
    parser.add_argument(
        "--repo-root",
        default=str(REPO_ROOT),
        help="Repository root path (default: inferred from script location)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    repo_root = Path(args.repo_root).expanduser().resolve()
    logs_dir = logs_dir_for_repo(repo_root)
    artifacts_dir = repo_root / "local" / "artifacts"
    logs_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    now = dt.datetime.now()
    tag = month_tag(now)
    timestamp = now.strftime("%Y%m%d_%H%M%S")
    log_path = logs_dir / f"{JOB_NAME}_{tag}_{timestamp}.log"
    artifact_path = artifacts_dir / f"{JOB_NAME}_{tag}_{timestamp}.json"

    tee_line(log_path, f"[{ts()}] RUN META: job={JOB_NAME} month={tag} force={bool(args.force_run)}")

    if skip_if_already_completed_for_period(
        log_path=log_path,
        log_dir=logs_dir,
        job_name=JOB_NAME,
        period_name="month",
        period_tag=tag,
        sentinel=COMPLETE_SENTINEL,
        force_run=bool(args.force_run),
    ):
        return 0

    try:
        accounts = resolve_accounts(args.accounts, load_runtime_eligible_account_names())
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if not accounts:
        print("No accounts specified.", file=sys.stderr)
        return 1

    conn = ensure_db()
    try:
        account_results: list[dict[str, object]] = []
        for account_name in accounts:
            account = find_account(conn, account_name)
            if account is None:
                tee_line(log_path, f"[{ts()}] WARN: account not found in DB: {account_name}")
                continue

            snapshot = fetch_latest_risk_snapshot(conn, account_id=account.id)
            if snapshot is None:
                account_results.append(
                    {
                        "account_name": account_name,
                        "snapshot_time": None,
                        "note": "no snapshot available",
                    }
                )
                tee_line(log_path, f"[{ts()}] RISK_REBASELINE: account={account_name} snapshot=none")
            else:
                account_results.append(
                    {
                        "account_name": account_name,
                        "snapshot_time": snapshot["snapshot_time"],
                        "gross_exposure": snapshot["gross_exposure"],
                        "net_exposure": snapshot["net_exposure"],
                        "drawdown_pct": snapshot["drawdown_pct"],
                        "daily_loss_pct": snapshot["daily_loss_pct"],
                        "kill_switch_triggered": bool(snapshot["kill_switch_triggered"]),
                        "max_symbol_concentration_pct": snapshot["max_symbol_concentration_pct"],
                        "max_sector_concentration_pct": snapshot["max_sector_concentration_pct"],
                    }
                )
                tee_line(
                    log_path,
                    (
                        f"[{ts()}] RISK_REBASELINE: account={account_name} "
                        f"snapshot_time={snapshot['snapshot_time']} "
                        f"kill_switch={bool(snapshot['kill_switch_triggered'])}"
                    ),
                )

        payload: dict[str, object] = {
            "month": tag,
            "generated_at": ts(),
            "accounts": account_results,
        }
        write_artifact(artifact_path, payload)
        tee_line(log_path, f"[{ts()}] {COMPLETE_SENTINEL}")
        return 0

    except Exception as exc:
        tee_line(log_path, f"[{ts()}] ERROR: {exc}")
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
