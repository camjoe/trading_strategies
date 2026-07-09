#!/usr/bin/env python3
"""M2 monthly governance job — active strategy parameter inventory for operator review."""

from __future__ import annotations

import json
from pathlib import Path

from common.paths.repo_paths import get_repo_root
from trading.interfaces.runtime.jobs.job_helpers import (
    already_completed_for_period,
    logs_dir_for_repo,
    ts,
)
from trading.interfaces.runtime.jobs.job_runner import JobContext, governance_job
from trading.interfaces.runtime.job_status import MONTHLY_GOVERNANCE_M2_PARAMETER_GOVERNANCE_COMPLETE_SENTINEL
from trading.repositories.strategy_param_sets import StrategyParamSetRepository
from trading.services.sleeves.book_assignments import list_report_books
from trading.services.accounts.queries import find_account

REPO_ROOT = get_repo_root(__file__)
LOGS_DIR = logs_dir_for_repo(REPO_ROOT)

COMPLETE_SENTINEL = MONTHLY_GOVERNANCE_M2_PARAMETER_GOVERNANCE_COMPLETE_SENTINEL

JOB_NAME = "monthly_governance_m2_parameter_governance"


def already_completed_this_month(log_dir: Path, tag: str) -> bool:
    return already_completed_for_period(
        log_dir=log_dir,
        job_name=JOB_NAME,
        period_tag=tag,
        sentinel=COMPLETE_SENTINEL,
    )


@governance_job(
    job_name=JOB_NAME,
    sentinel=COMPLETE_SENTINEL,
    period="month",
    description="M2 monthly governance: inventory active strategy parameters per sleeve.",
)
def main(ctx: JobContext) -> dict[str, object]:
    account_results: list[dict[str, object]] = []
    for account_name in ctx.accounts:
        account = find_account(ctx.conn, account_name)
        if account is None:
            ctx.log(f"WARN: account not found in DB: {account_name}")
            continue

        param_set_repo = StrategyParamSetRepository(ctx.conn)
        book_rows: list[dict[str, object]] = []

        for book, assignment in list_report_books(ctx.conn, account_id=account.id):
            strategy_name: str | None = None
            param_set_id: int | None = None
            params: object = None

            if assignment is not None:
                strategy_name = assignment.strategy_name
                if assignment.param_set_id is not None:
                    param_set_id = assignment.param_set_id
                    param_set = param_set_repo.fetch_by_id(param_set_id=param_set_id)
                    if param_set is not None:
                        try:
                            params = json.loads(param_set.params_json) if param_set.params_json else None
                        except ValueError, TypeError:
                            params = None

            book_rows.append(
                {
                    "book_name": book.name,
                    "strategy_name": strategy_name,
                    "param_set_id": param_set_id,
                    "params": params,
                }
            )

        account_results.append({"account_name": account_name, "books": book_rows})
        ctx.log(f"PARAM_GOVERNANCE: account={account_name} books={len(book_rows)}")

    return {
        "month": ctx.tag,
        "generated_at": ts(),
        "accounts": account_results,
    }


if __name__ == "__main__":
    raise SystemExit(main())
