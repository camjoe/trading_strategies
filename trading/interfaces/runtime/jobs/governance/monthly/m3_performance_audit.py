#!/usr/bin/env python3
"""M3 monthly governance job — 90-day long-horizon performance audit across all sleeves."""

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
from trading.interfaces.runtime.job_status import MONTHLY_GOVERNANCE_M3_PERFORMANCE_AUDIT_COMPLETE_SENTINEL
from trading.services.performance import fetch_sleeve_performance_window
from trading.repositories.sleeves import SleeveRepository
from trading.services.accounts import load_runtime_eligible_account_names
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="M3 monthly governance: 90-day long-horizon performance audit across all sleeves.",
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
    parser.add_argument(
        "--audit-window-days",
        type=int,
        default=90,
        help="Historical lookback window in days for the performance audit (default: 90)",
    )
    return parser.parse_args()


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


def main() -> int:
    args = parse_args()

    if int(args.audit_window_days) < 1:
        print("--audit-window-days must be >= 1", file=sys.stderr)
        return 1

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
        audit_window_days = int(args.audit_window_days)
        today = now.date()
        today_str = today.isoformat()
        start_str = (today - dt.timedelta(days=audit_window_days - 1)).isoformat()

        account_results: list[dict[str, object]] = []
        for account_name in accounts:
            account = find_account(conn, account_name)
            if account is None:
                tee_line(log_path, f"[{ts()}] WARN: account not found in DB: {account_name}")
                continue

            sleeve_repo = SleeveRepository(conn)
            sleeves = sleeve_repo.fetch_for_account(account_id=account.id)
            sleeve_rows: list[dict[str, object]] = []

            for sleeve in sleeves:
                assignment = sleeve_repo.fetch_active_assignment(sleeve_id=sleeve.id)
                strategy_name = assignment.strategy_name if assignment is not None else None

                metrics = fetch_sleeve_performance_window(
                    conn,
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
            tee_line(
                log_path,
                (
                    f"[{ts()}] PERFORMANCE_AUDIT: account={account_name} "
                    f"sleeves={len(sleeve_rows)} window_days={audit_window_days}"
                ),
            )

        payload: dict[str, object] = {
            "month": tag,
            "generated_at": ts(),
            "audit_window_days": audit_window_days,
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
