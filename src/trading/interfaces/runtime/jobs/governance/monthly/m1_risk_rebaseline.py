#!/usr/bin/env python3
"""M1 monthly governance job — risk budget rebaseline report for operator review."""

from __future__ import annotations

from common.git import get_repo_root
from common.runtime_job_status import MONTHLY_GOVERNANCE_M1_RISK_REBASELINE_COMPLETE_SENTINEL
from trading.interfaces.runtime.jobs.job_helpers import (
    logs_dir_for_repo,
    ts,
)
from trading.interfaces.runtime.jobs.job_runner import JobContext, governance_job
from trading.services.accounts.queries import find_account
from trading.services.analysis.risk_snapshots import fetch_latest_risk_snapshot

REPO_ROOT = get_repo_root(__file__)
LOGS_DIR = logs_dir_for_repo(REPO_ROOT)

COMPLETE_SENTINEL = MONTHLY_GOVERNANCE_M1_RISK_REBASELINE_COMPLETE_SENTINEL

JOB_NAME = "monthly_governance_m1_risk_rebaseline"


@governance_job(
    job_name=JOB_NAME,
    sentinel=COMPLETE_SENTINEL,
    period="month",
    description="M1 monthly governance: risk budget rebaseline report per account.",
)
def main(ctx: JobContext) -> dict[str, object]:
    account_results: list[dict[str, object]] = []
    for account_name in ctx.accounts:
        account = find_account(ctx.db, account_name)
        if account is None:
            ctx.log(f"WARN: account not found in DB: {account_name}")
            continue

        snapshot = fetch_latest_risk_snapshot(ctx.db, account_id=account.id)
        if snapshot is None:
            account_results.append(
                {
                    "account_name": account_name,
                    "snapshot_time": None,
                    "note": "no snapshot available",
                }
            )
            ctx.log(f"RISK_REBASELINE: account={account_name} snapshot=none")
        else:
            account_results.append(
                {
                    "account_name": account_name,
                    "snapshot_time": snapshot.snapshot_time,
                    "gross_exposure": snapshot.gross_exposure,
                    "net_exposure": snapshot.net_exposure,
                    "drawdown_pct": snapshot.drawdown_pct,
                    "daily_loss_pct": snapshot.daily_loss_pct,
                    "kill_switch_triggered": snapshot.kill_switch_triggered,
                    "max_symbol_concentration_pct": snapshot.max_symbol_concentration_pct,
                    "max_sector_concentration_pct": snapshot.max_sector_concentration_pct,
                }
            )
            ctx.log(
                f"RISK_REBASELINE: account={account_name} "
                f"snapshot_time={snapshot.snapshot_time} "
                f"kill_switch={snapshot.kill_switch_triggered}"
            )

    return {
        "month": ctx.tag,
        "generated_at": ts(),
        "accounts": account_results,
    }


if __name__ == "__main__":
    raise SystemExit(main())
