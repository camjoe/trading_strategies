#!/usr/bin/env python3
"""M3 monthly governance job — 90-day long-horizon performance audit across all sleeves."""

from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

from common.paths.repo_paths import get_repo_root
from trading.interfaces.runtime.jobs.job_helpers import (
    already_completed_for_period,
    logs_dir_for_repo,
    ts,
)
from trading.interfaces.runtime.jobs.job_runner import JobContext, governance_job
from trading.interfaces.runtime.job_status import MONTHLY_GOVERNANCE_M3_PERFORMANCE_AUDIT_COMPLETE_SENTINEL
from trading.services.analysis import fetch_sleeve_performance_window
from trading.repositories.sleeves import SleeveRepository
from trading.services.accounts.queries import find_account

REPO_ROOT = get_repo_root(__file__)
LOGS_DIR = logs_dir_for_repo(REPO_ROOT)

COMPLETE_SENTINEL = MONTHLY_GOVERNANCE_M3_PERFORMANCE_AUDIT_COMPLETE_SENTINEL

JOB_NAME = "monthly_governance_m3_performance_audit"


def already_completed_this_month(log_dir: Path, tag: str) -> bool:
    return already_completed_for_period(
        log_dir=log_dir,
        job_name=JOB_NAME,
        period_tag=tag,
        sentinel=COMPLETE_SENTINEL,
    )


def _add_audit_window_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--audit-window-days",
        type=int,
        default=90,
        help="Historical lookback window in days for the performance audit (default: 90)",
    )


def _validate_args(args: argparse.Namespace) -> str | None:
    if int(args.audit_window_days) < 1:
        return "--audit-window-days must be >= 1"
    return None


def _compute_audit_stats(metrics: list) -> dict[str, object]:
    """Compute long-horizon performance summary from daily metric rows."""
    # Cumulative return: compound of all non-null return_pct values.
    returns = [row.return_pct for row in metrics if row.return_pct is not None]
    cumulative_return_pct: float | None
    if returns:
        compound = 1.0
        for r in returns:
            compound *= 1.0 + r / 100.0
        cumulative_return_pct = (compound - 1.0) * 100.0
    else:
        cumulative_return_pct = None

    # Max drawdown: minimum (most negative) drawdown_pct value.
    drawdowns = [row.drawdown_pct for row in metrics if row.drawdown_pct is not None]
    max_drawdown_pct = min(drawdowns) if drawdowns else None

    # Average hit rate.
    hit_rates = [row.hit_rate for row in metrics if row.hit_rate is not None]
    avg_hit_rate = (sum(hit_rates) / len(hit_rates)) if hit_rates else None

    # Total trades.
    trade_counts = [row.trade_count for row in metrics if row.trade_count is not None]
    total_trades = sum(trade_counts)

    return {
        "data_points": len(metrics),
        "cumulative_return_pct": cumulative_return_pct,
        "max_drawdown_pct": max_drawdown_pct,
        "avg_hit_rate": avg_hit_rate,
        "total_trades": total_trades,
    }


@governance_job(
    job_name=JOB_NAME,
    sentinel=COMPLETE_SENTINEL,
    period="month",
    description="M3 monthly governance: 90-day long-horizon performance audit across all sleeves.",
    add_arguments=_add_audit_window_arg,
    validate=_validate_args,
)
def main(ctx: JobContext) -> dict[str, object]:
    audit_window_days = int(ctx.args.audit_window_days)
    today = ctx.now.date()
    today_str = today.isoformat()
    start_str = (today - dt.timedelta(days=audit_window_days - 1)).isoformat()

    account_results: list[dict[str, object]] = []
    for account_name in ctx.accounts:
        account = find_account(ctx.conn, account_name)
        if account is None:
            ctx.log(f"WARN: account not found in DB: {account_name}")
            continue

        sleeve_repo = SleeveRepository(ctx.conn)
        sleeves = sleeve_repo.fetch_for_account(account_id=account.id)
        sleeve_rows: list[dict[str, object]] = []

        for sleeve in sleeves:
            assignment = sleeve_repo.fetch_active_assignment(sleeve_id=sleeve.id)
            strategy_name = assignment.strategy_name if assignment is not None else None

            metrics = fetch_sleeve_performance_window(
                ctx.conn,
                sleeve_id=sleeve.id,
                start_date=start_str,
                end_date=today_str,
            )
            stats = _compute_audit_stats(metrics)

            sleeve_rows.append(
                {
                    "sleeve_name": sleeve.name,
                    "strategy_name": strategy_name,
                    **stats,
                }
            )

        account_results.append({"account_name": account_name, "sleeves": sleeve_rows})
        ctx.log(
            f"PERFORMANCE_AUDIT: account={account_name} sleeves={len(sleeve_rows)} window_days={audit_window_days}"
        )

    return {
        "month": ctx.tag,
        "generated_at": ts(),
        "audit_window_days": audit_window_days,
        "accounts": account_results,
    }


if __name__ == "__main__":
    raise SystemExit(main())
