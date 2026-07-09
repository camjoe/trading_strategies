#!/usr/bin/env python3
"""W2 weekly governance job — promotion/retirement review for each account."""

from __future__ import annotations

from pathlib import Path

from common.paths.repo_paths import get_repo_root
from trading.interfaces.runtime.jobs.governance.payload_models import (
    WeeklyPromotionAccountPayload,
    WeeklyPromotionArtifactPayload,
    WeeklyPromotionSleevePayload,
)
from trading.interfaces.runtime.jobs.job_helpers import (
    already_completed_for_period,
    logs_dir_for_repo,
    ts,
)
from trading.interfaces.runtime.jobs.job_runner import JobContext, governance_job
from trading.interfaces.runtime.job_status import WEEKLY_GOVERNANCE_W2_PROMOTION_REVIEW_COMPLETE_SENTINEL
from trading.services.sleeves.book_assignments import list_report_books
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


@governance_job(
    job_name=JOB_NAME,
    sentinel=COMPLETE_SENTINEL,
    period="week",
    description="W2 weekly governance: promotion/retirement review for runtime-eligible accounts.",
)
def main(ctx: JobContext) -> dict[str, object]:
    account_results: list[WeeklyPromotionAccountPayload] = []
    for account_name in ctx.accounts:
        account = find_account(ctx.conn, account_name)
        if account is None:
            ctx.log(f"WARN: account not found in DB: {account_name}")
            continue

        assessment = fetch_current_promotion_assessment(ctx.conn, account_name=account_name)

        book_rows: list[WeeklyPromotionSleevePayload] = []
        for book, assignment in list_report_books(ctx.conn, account_id=account.id):
            strategy_name = assignment.strategy_name if assignment is not None else None

            book_rows.append(
                WeeklyPromotionSleevePayload(
                    book_name=book.name,
                    strategy_name=strategy_name,
                    book_status=book.status,
                )
            )

        account_results.append(
            WeeklyPromotionAccountPayload(
                account_name=account_name,
                ready_for_live=bool(assessment.ready_for_live),
                blockers=list(assessment.blockers),
                books=book_rows,
            )
        )
        ctx.log(
            f"PROMOTION_REVIEW: account={account_name} "
            f"ready_for_live={assessment.ready_for_live} "
            f"blockers={len(assessment.blockers)}"
        )

    payload = WeeklyPromotionArtifactPayload(
        week=ctx.tag,
        generated_at=ts(),
        accounts=account_results,
    )
    return payload.as_dict()


if __name__ == "__main__":
    raise SystemExit(main())
