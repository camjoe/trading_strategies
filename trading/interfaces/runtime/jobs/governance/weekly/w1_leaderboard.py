#!/usr/bin/env python3
"""W1 weekly governance job — strategy parameter leaderboard ranked by 30-day performance."""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from dataclasses import replace
from pathlib import Path
from typing import TypedDict

from common.paths.repo_paths import get_repo_root
from trading.database.db_init import ensure_db
from trading.interfaces.runtime.jobs.governance.payload_models import (
    WeeklyLeaderboardAccountPayload,
    WeeklyLeaderboardArtifactPayload,
    WeeklyLeaderboardSleevePayload,
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
from trading.interfaces.runtime.job_status import WEEKLY_GOVERNANCE_W1_LEADERBOARD_COMPLETE_SENTINEL
from trading.services.performance import fetch_sleeve_performance_window
from trading.services.accounts.queries import find_account
from trading.repositories.sleeves import (
    fetch_active_sleeve_strategy_assignment,
    fetch_strategy_sleeves_for_account,
)
from trading.services.accounts import load_runtime_eligible_account_names

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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="W1 weekly governance: rank strategy sleeves by 30-day performance.",
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
        "--window-days",
        type=int,
        default=30,
        help="Lookback window in days for performance metrics (default: 30)",
    )
    return parser.parse_args()


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


def main() -> int:
    args = parse_args()

    if int(args.window_days) < 1:
        print("--window-days must be >= 1", file=sys.stderr)
        return 1

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
        window_days = int(args.window_days)
        today = now.date()
        today_str = today.isoformat()
        start_str = (today - dt.timedelta(days=window_days - 1)).isoformat()

        account_results: list[WeeklyLeaderboardAccountPayload] = []
        for account_name in accounts:
            account = find_account(conn, account_name)
            if account is None:
                tee_line(log_path, f"[{ts()}] WARN: account not found in DB: {account_name}")
                continue

            sleeves = fetch_strategy_sleeves_for_account(conn, account_id=account.id)
            sleeve_rows: list[WeeklyLeaderboardSleevePayload] = []

            for sleeve in sleeves:
                sleeve_id = int(sleeve["id"])
                sleeve_name = str(sleeve["name"])

                assignment = fetch_active_sleeve_strategy_assignment(conn, sleeve_id=sleeve_id)
                strategy_name = str(assignment["strategy_name"]) if assignment is not None else None

                metrics = fetch_sleeve_performance_window(
                    conn,
                    sleeve_id=sleeve_id,
                    start_date=start_str,
                    end_date=today_str,
                )
                stats = _compute_sleeve_stats(metrics)
                sleeve_rows.append(
                    WeeklyLeaderboardSleevePayload(
                        sleeve_name=sleeve_name,
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
            sleeve_rows.sort(
                key=lambda r: (
                    float(r.avg_risk_adjusted_score) if r.avg_risk_adjusted_score is not None else float("-inf")
                ),
                reverse=True,
            )
            ranked_sleeves = [replace(sleeve_row, rank=rank) for rank, sleeve_row in enumerate(sleeve_rows, start=1)]

            account_results.append(
                WeeklyLeaderboardAccountPayload(
                    account_name=account_name,
                    sleeves=ranked_sleeves,
                )
            )
            tee_line(
                log_path,
                f"[{ts()}] LEADERBOARD: account={account_name} sleeves={len(sleeve_rows)}",
            )

        payload = WeeklyLeaderboardArtifactPayload(
            week=tag,
            generated_at=ts(),
            window_days=window_days,
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
