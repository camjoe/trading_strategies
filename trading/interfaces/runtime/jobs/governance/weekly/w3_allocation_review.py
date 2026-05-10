#!/usr/bin/env python3
"""W3 weekly governance job — allocation reweight review comparing actual vs target sleeve NAV."""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

from common.paths.repo_paths import get_repo_root
from trading.database.db_init import ensure_db
from trading.interfaces.runtime.jobs.governance.payload_models import (
    WeeklyAllocationAccountPayload,
    WeeklyAllocationArtifactPayload,
    WeeklyAllocationSleevePayload,
)
from trading.interfaces.runtime.jobs.job_helpers import (
    already_completed_for_period,
    logs_dir_for_repo,
    resolve_accounts,
    skip_if_already_completed_for_period,
    tee_line,
    ts,
    week_tag,
    write_artifact,
)
from trading.interfaces.runtime.job_status import WEEKLY_GOVERNANCE_W3_ALLOCATION_REVIEW_COMPLETE_SENTINEL
from trading.repositories.accounts import fetch_account_by_name
from trading.repositories.sleeves import fetch_strategy_sleeves_for_account
from trading.services.accounts import load_runtime_eligible_account_names

REPO_ROOT = get_repo_root(__file__)
LOGS_DIR = logs_dir_for_repo(REPO_ROOT)

COMPLETE_SENTINEL = WEEKLY_GOVERNANCE_W3_ALLOCATION_REVIEW_COMPLETE_SENTINEL

JOB_NAME = "weekly_governance_w3_allocation_review"
def already_completed_this_week(log_dir: Path, tag: str) -> bool:
    return already_completed_for_period(
        log_dir=log_dir,
        job_name=JOB_NAME,
        period_tag=tag,
        sentinel=COMPLETE_SENTINEL,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="W3 weekly governance: compare actual sleeve NAV allocation vs original start_equity ratios.",
    )
    parser.add_argument(
        "--accounts",
        default="all",
        help="Comma-separated account names, or 'all' (default: all)",
    )
    parser.add_argument("--force-run", action="store_true", help="Allow duplicate same-week run")
    parser.add_argument(
        "--repo-root",
        default=str(REPO_ROOT),
        help="Repository root path (default: inferred from script location)",
    )
    parser.add_argument(
        "--drift-threshold-pct",
        type=float,
        default=5.0,
        help="Drift threshold percentage to flag reweight suggestion (default: 5.0)",
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
    tag = week_tag(now)
    timestamp = now.strftime("%Y%m%d_%H%M%S")
    log_path = logs_dir / f"{JOB_NAME}_{tag}_{timestamp}.log"
    artifact_path = artifacts_dir / f"{JOB_NAME}_{tag}_{timestamp}.json"

    drift_threshold = float(args.drift_threshold_pct)

    tee_line(log_path, f"[{ts()}] RUN META: job={JOB_NAME} week={tag} force={bool(args.force_run)}")

    if skip_if_already_completed_for_period(
        log_path=log_path,
        log_dir=logs_dir,
        job_name=JOB_NAME,
        period_name="week",
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
        account_results: list[WeeklyAllocationAccountPayload] = []
        for account_name in accounts:
            account = fetch_account_by_name(conn, account_name)
            if account is None:
                tee_line(log_path, f"[{ts()}] WARN: account not found in DB: {account_name}")
                continue

            sleeves = fetch_strategy_sleeves_for_account(conn, account_id=account.id)

            # current_equity already includes cash for each sleeve.
            current_navs = [
                float(sleeve["current_equity"])
                for sleeve in sleeves
            ]
            total_nav = sum(current_navs)

            # Compute target allocation from original start_equity.
            start_equities = [float(sleeve["start_equity"]) for sleeve in sleeves]
            total_start_equity = sum(start_equities)

            sleeve_rows: list[WeeklyAllocationSleevePayload] = []
            for sleeve, current_nav, start_equity in zip(sleeves, current_navs, start_equities):
                current_pct = (current_nav / total_nav * 100.0) if total_nav != 0.0 else 0.0
                target_pct = (start_equity / total_start_equity * 100.0) if total_start_equity != 0.0 else 0.0
                drift_pct = current_pct - target_pct
                reweight_suggested = abs(drift_pct) >= drift_threshold

                sleeve_rows.append(
                    WeeklyAllocationSleevePayload(
                        sleeve_name=str(sleeve["name"]),
                        current_nav=current_nav,
                        current_pct=current_pct,
                        target_pct=target_pct,
                        drift_pct=drift_pct,
                        reweight_suggested=reweight_suggested,
                    )
                )

            account_results.append(
                WeeklyAllocationAccountPayload(
                    account_name=account_name,
                    total_nav=total_nav,
                    sleeves=sleeve_rows,
                )
            )
            reweight_count = sum(1 for s in sleeve_rows if s.reweight_suggested)
            tee_line(
                log_path,
                (
                    f"[{ts()}] ALLOCATION_REVIEW: account={account_name} "
                    f"total_nav={total_nav:.2f} "
                    f"sleeves={len(sleeve_rows)} reweight_suggested={reweight_count}"
                ),
            )

        payload = WeeklyAllocationArtifactPayload(
            week=tag,
            generated_at=ts(),
            drift_threshold_pct=drift_threshold,
            accounts=account_results,
        )
        write_artifact(artifact_path, payload.as_dict())
        tee_line(log_path, f"[{ts()}] {COMPLETE_SENTINEL}")
        return 0

    except Exception as exc:
        tee_line(log_path, f"[{ts()}] ERROR: {exc}")
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
