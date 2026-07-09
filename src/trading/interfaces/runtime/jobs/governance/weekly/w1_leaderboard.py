#!/usr/bin/env python3
"""W1 weekly governance job — strategy parameter leaderboard ranked by 30-day performance."""

from __future__ import annotations

import argparse
import datetime as dt
from dataclasses import replace
from pathlib import Path
from typing import TypedDict

from common.paths.repo_paths import get_repo_root
from trading.interfaces.runtime.jobs.governance.payload_models import (
    WeeklyLeaderboardAccountPayload,
    WeeklyLeaderboardArtifactPayload,
    WeeklyLeaderboardSleevePayload,
)
from trading.interfaces.runtime.jobs.job_helpers import (
    already_completed_for_period,
    logs_dir_for_repo,
    ts,
)
from trading.interfaces.runtime.jobs.job_runner import JobContext, governance_job
from trading.interfaces.runtime.job_status import WEEKLY_GOVERNANCE_W1_LEADERBOARD_COMPLETE_SENTINEL
from trading.services.analysis import fetch_book_performance_window
from trading.services.sleeves.book_assignments import list_report_books
from trading.services.accounts.queries import find_account

REPO_ROOT = get_repo_root(__file__)
LOGS_DIR = logs_dir_for_repo(REPO_ROOT)

COMPLETE_SENTINEL = WEEKLY_GOVERNANCE_W1_LEADERBOARD_COMPLETE_SENTINEL

JOB_NAME = "weekly_governance_w1_leaderboard"


def already_completed_this_week(log_dir: Path, tag: str) -> bool:
    return already_completed_for_period(
        log_dir=log_dir,
        job_name=JOB_NAME,
        period_tag=tag,
        sentinel=COMPLETE_SENTINEL,
    )


def _add_window_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--window-days",
        type=int,
        default=30,
        help="Lookback window in days for performance metrics (default: 30)",
    )


def _validate_args(args: argparse.Namespace) -> str | None:
    if int(args.window_days) < 1:
        return "--window-days must be >= 1"
    return None


class SleeveStats(TypedDict):
    avg_return_pct: float | None
    avg_risk_adjusted_score: float | None
    max_drawdown_pct: float | None
    total_trade_count: int
    data_points: int


def _compute_sleeve_stats(metrics: list) -> SleeveStats:
    """Compute aggregated performance stats from a list of daily metric rows."""
    returns = [row.return_pct for row in metrics if row.return_pct is not None]
    risk_scores = [row.risk_adjusted_score for row in metrics if row.risk_adjusted_score is not None]
    drawdowns = [row.drawdown_pct for row in metrics if row.drawdown_pct is not None]
    trade_counts = [row.trade_count for row in metrics if row.trade_count is not None]

    return {
        "avg_return_pct": (sum(returns) / len(returns)) if returns else None,
        "avg_risk_adjusted_score": (sum(risk_scores) / len(risk_scores)) if risk_scores else None,
        "max_drawdown_pct": min(drawdowns) if drawdowns else None,
        "total_trade_count": sum(trade_counts) if trade_counts else 0,
        "data_points": len(metrics),
    }


@governance_job(
    job_name=JOB_NAME,
    sentinel=COMPLETE_SENTINEL,
    period="week",
    description="W1 weekly governance: rank strategy sleeves by 30-day performance.",
    add_arguments=_add_window_arg,
    validate=_validate_args,
)
def main(ctx: JobContext) -> dict[str, object]:
    window_days = int(ctx.args.window_days)
    today = ctx.now.date()
    today_str = today.isoformat()
    start_str = (today - dt.timedelta(days=window_days - 1)).isoformat()

    account_results: list[WeeklyLeaderboardAccountPayload] = []
    for account_name in ctx.accounts:
        account = find_account(ctx.conn, account_name)
        if account is None:
            ctx.log(f"WARN: account not found in DB: {account_name}")
            continue

        book_rows: list[WeeklyLeaderboardSleevePayload] = []

        for book, assignment in list_report_books(ctx.conn, account_id=account.id):
            strategy_name = assignment.strategy_name if assignment is not None else None

            metrics = fetch_book_performance_window(
                ctx.conn,
                book_id=book.id,
                start_date=start_str,
                end_date=today_str,
            )
            stats = _compute_sleeve_stats(metrics)
            book_rows.append(
                WeeklyLeaderboardSleevePayload(
                    book_name=book.name,
                    strategy_name=strategy_name,
                    avg_return_pct=stats["avg_return_pct"],
                    avg_risk_adjusted_score=stats["avg_risk_adjusted_score"],
                    max_drawdown_pct=stats["max_drawdown_pct"],
                    total_trade_count=stats["total_trade_count"],
                    data_points=stats["data_points"],
                    rank=0,
                )
            )

        # Sort by avg_risk_adjusted_score descending; nulls last.
        book_rows.sort(
            key=lambda r: float(r.avg_risk_adjusted_score) if r.avg_risk_adjusted_score is not None else float("-inf"),
            reverse=True,
        )
        ranked_books = [replace(book_row, rank=rank) for rank, book_row in enumerate(book_rows, start=1)]

        account_results.append(
            WeeklyLeaderboardAccountPayload(
                account_name=account_name,
                books=ranked_books,
            )
        )
        ctx.log(f"LEADERBOARD: account={account_name} books={len(book_rows)}")

    payload = WeeklyLeaderboardArtifactPayload(
        week=ctx.tag,
        generated_at=ts(),
        window_days=window_days,
        accounts=account_results,
    )
    return payload.as_dict()


if __name__ == "__main__":
    raise SystemExit(main())
