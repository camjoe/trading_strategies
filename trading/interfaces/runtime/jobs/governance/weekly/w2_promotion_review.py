#!/usr/bin/env python3
"""W2 weekly governance job — promotion/retirement review for each account."""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

from common.paths.repo_paths import get_repo_root
from trading.database.db_init import ensure_db
from trading.interfaces.runtime.jobs.governance.payload_models import (
    WeeklyPromotionAccountPayload,
    WeeklyPromotionArtifactPayload,
    WeeklyPromotionSleevePayload,
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
from trading.interfaces.runtime.job_status import WEEKLY_GOVERNANCE_W2_PROMOTION_REVIEW_COMPLETE_SENTINEL
from trading.repositories.sleeves import (
    fetch_active_sleeve_strategy_assignment,
    fetch_strategy_sleeves_for_account,
)
from trading.services.accounts import load_runtime_eligible_account_names
from trading.services.accounts.queries import find_account
from trading.services.promotion.assessment import fetch_current_promotion_assessment

REPO_ROOT = get_repo_root(__file__)
LOGS_DIR = logs_dir_for_repo(REPO_ROOT)

COMPLETE_SENTINEL = WEEKLY_GOVERNANCE_W2_PROMOTION_REVIEW_COMPLETE_SENTINEL

JOB_NAME = "weekly_governance_w2_promotion_review"


def already_completed_this_week(log_dir: Path, tag: str) -> bool:
    return already_completed_for_period(
        log_dir=log_dir,
        job_name=JOB_NAME,
        period_tag=tag,
        sentinel=COMPLETE_SENTINEL,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="W2 weekly governance: promotion/retirement review for runtime-eligible accounts.",
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
        account_results: list[WeeklyPromotionAccountPayload] = []
        for account_name in accounts:
            account = find_account(conn, account_name)
            if account is None:
                tee_line(log_path, f"[{ts()}] WARN: account not found in DB: {account_name}")
                continue

            assessment = fetch_current_promotion_assessment(conn, account_name=account_name)

            sleeves = fetch_strategy_sleeves_for_account(conn, account_id=account.id)
            sleeve_rows: list[WeeklyPromotionSleevePayload] = []
            for sleeve in sleeves:
                sleeve_id = int(sleeve["id"])
                sleeve_name = str(sleeve["name"])
                sleeve_status = str(sleeve["status"])

                assignment = fetch_active_sleeve_strategy_assignment(conn, sleeve_id=sleeve_id)
                strategy_name = str(assignment["strategy_name"]) if assignment is not None else None

                sleeve_rows.append(
                    WeeklyPromotionSleevePayload(
                        sleeve_name=sleeve_name,
                        strategy_name=strategy_name,
                        sleeve_status=sleeve_status,
                    )
                )

            account_results.append(
                WeeklyPromotionAccountPayload(
                    account_name=account_name,
                    ready_for_live=bool(assessment.ready_for_live),
                    blockers=list(assessment.blockers),
                    sleeves=sleeve_rows,
                )
            )
            tee_line(
                log_path,
                (
                    f"[{ts()}] PROMOTION_REVIEW: account={account_name} "
                    f"ready_for_live={assessment.ready_for_live} "
                    f"blockers={len(assessment.blockers)}"
                ),
            )

        payload = WeeklyPromotionArtifactPayload(
            week=tag,
            generated_at=ts(),
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
