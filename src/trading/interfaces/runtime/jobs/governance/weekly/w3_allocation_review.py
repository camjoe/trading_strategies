#!/usr/bin/env python3
"""W3 weekly governance job — allocation reweight review comparing actual vs target sleeve NAV."""

from __future__ import annotations

import argparse
from pathlib import Path

from common.paths.repo_paths import get_repo_root
from trading.interfaces.runtime.jobs.governance.payload_models import (
    WeeklyAllocationAccountPayload,
    WeeklyAllocationArtifactPayload,
    WeeklyAllocationSleevePayload,
)
from trading.interfaces.runtime.jobs.job_helpers import (
    already_completed_for_period,
    logs_dir_for_repo,
    ts,
)
from trading.interfaces.runtime.jobs.job_runner import JobContext, governance_job
from trading.interfaces.runtime.job_status import WEEKLY_GOVERNANCE_W3_ALLOCATION_REVIEW_COMPLETE_SENTINEL
from trading.repositories.sleeves import SleeveRepository
from trading.services.accounts.queries import find_account

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


def _add_drift_threshold_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--drift-threshold-pct",
        type=float,
        default=5.0,
        help="Drift threshold percentage to flag reweight suggestion (default: 5.0)",
    )


@governance_job(
    job_name=JOB_NAME,
    sentinel=COMPLETE_SENTINEL,
    period="week",
    description="W3 weekly governance: compare actual sleeve NAV allocation vs original start_equity ratios.",
    add_arguments=_add_drift_threshold_arg,
)
def main(ctx: JobContext) -> dict[str, object]:
    drift_threshold = float(ctx.args.drift_threshold_pct)

    account_results: list[WeeklyAllocationAccountPayload] = []
    for account_name in ctx.accounts:
        account = find_account(ctx.conn, account_name)
        if account is None:
            ctx.log(f"WARN: account not found in DB: {account_name}")
            continue

        sleeves = SleeveRepository(ctx.conn).fetch_for_account(account_id=account.id)

        # current_equity already includes cash for each sleeve.
        current_navs = [s.current_equity for s in sleeves]
        total_nav = sum(current_navs)

        # Compute target allocation from original start_equity.
        start_equities = [s.start_equity for s in sleeves]
        total_start_equity = sum(start_equities)

        sleeve_rows: list[WeeklyAllocationSleevePayload] = []
        for sleeve, current_nav, start_equity in zip(sleeves, current_navs, start_equities):
            current_pct = (current_nav / total_nav * 100.0) if total_nav != 0.0 else 0.0
            target_pct = (start_equity / total_start_equity * 100.0) if total_start_equity != 0.0 else 0.0
            drift_pct = current_pct - target_pct
            reweight_suggested = abs(drift_pct) >= drift_threshold

            sleeve_rows.append(
                WeeklyAllocationSleevePayload(
                    sleeve_name=sleeve.name,
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
        ctx.log(
            f"ALLOCATION_REVIEW: account={account_name} "
            f"total_nav={total_nav:.2f} "
            f"sleeves={len(sleeve_rows)} reweight_suggested={reweight_count}"
        )

    payload = WeeklyAllocationArtifactPayload(
        week=ctx.tag,
        generated_at=ts(),
        drift_threshold_pct=drift_threshold,
        accounts=account_results,
    )
    return payload.as_dict()


if __name__ == "__main__":
    raise SystemExit(main())
