#!/usr/bin/env python3
"""Run daily challenger shadow evaluation and write account-level artifacts."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from common.paths.repo_paths import get_repo_root
from src.infrastructure.database.db_init import ensure_db
from trading.interfaces.runtime.jobs.job_helpers import (
    day_tag,
    is_env_truthy,
    latest_log_contains_sentinel,
    logs_dir_for_repo,
    resolve_accounts,
    tee_line,
    ts,
    write_artifact,
)
from trading.interfaces.runtime.job_status import (
    DAILY_CHALLENGER_SHADOW_EVAL_COMPLETE_SENTINEL,
)
from trading.services.accounts import get_account, load_runtime_eligible_account_names
from trading.services.sleeves.shadow_evaluation import (
    DEFAULT_SHADOW_ROLLING_WINDOW_DAYS,
    ShadowEvaluationRun,
    build_sleeve_shadow_evaluation,
)

REPO_ROOT = get_repo_root(__file__)
LOGS_DIR = logs_dir_for_repo(REPO_ROOT)

# Explicit opt-in env var so shadow evaluation runs remain operator-controlled.
CHALLENGER_SHADOW_EVAL_ENABLED_ENV = "DAILY_CHALLENGER_SHADOW_EVAL_ENABLED"

# Successful daily runs write this sentinel into the newest log.
COMPLETE_SENTINEL = DAILY_CHALLENGER_SHADOW_EVAL_COMPLETE_SENTINEL


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run daily challenger shadow evaluation for runtime-eligible accounts.",
    )
    parser.add_argument(
        "--accounts",
        default="all",
        help="Comma-separated account names, or 'all' for every account in DB (default: all)",
    )
    parser.add_argument("--force-run", action="store_true", help="Allow duplicate same-day run")
    parser.add_argument("--run-source", default="daily-challenger-shadow-eval")
    parser.add_argument(
        "--enable-run",
        action="store_true",
        help="Explicitly enable challenger shadow evaluation for this invocation",
    )
    parser.add_argument(
        "--rolling-window-days",
        type=int,
        default=DEFAULT_SHADOW_ROLLING_WINDOW_DAYS,
        help=(
            "Historical lookback window in days for challenger evidence "
            f"(default: {DEFAULT_SHADOW_ROLLING_WINDOW_DAYS})"
        ),
    )
    parser.add_argument(
        "--repo-root",
        default=str(REPO_ROOT),
        help="Repository root path (default: inferred from script location)",
    )
    return parser.parse_args()


def is_run_enabled(args: argparse.Namespace) -> bool:
    if bool(args.enable_run):
        return True
    return is_env_truthy(CHALLENGER_SHADOW_EVAL_ENABLED_ENV)


def already_completed_today(log_dir: Path, day_tag_str: str) -> bool:
    return latest_log_contains_sentinel(
        log_dir,
        f"daily_challenger_shadow_eval_{day_tag_str}_*.log",
        COMPLETE_SENTINEL,
    )


def _serialize_shadow_run(result: ShadowEvaluationRun) -> dict[str, object]:
    return {
        "account_id": result.account_id,
        "account_name": result.account_name,
        "window_start_day": result.window_start_day,
        "window_end_day": result.window_end_day,
        "sleeves": [
            {
                "sleeve_id": sleeve.sleeve_id,
                "incumbent_strategy": sleeve.incumbent_strategy,
                "challenger_count": len(sleeve.challengers),
                "challengers": [
                    {
                        "strategy_name": challenger.strategy_name,
                        "param_set_id": challenger.param_set_id,
                        "trade_count": challenger.trade_count,
                        "risk_adjusted_return": challenger.risk_adjusted_return,
                        "stability": challenger.stability,
                        "drawdown_penalty": challenger.drawdown_penalty,
                        "cost_penalty": challenger.cost_penalty,
                        "regime_fit": challenger.regime_fit,
                    }
                    for challenger in sleeve.challengers
                ],
            }
            for sleeve in result.sleeves
        ],
    }


def run_shadow_eval_for_account(
    conn,
    *,
    account_name: str,
    rolling_window_days: int,
    as_of_iso: str,
) -> ShadowEvaluationRun:
    account = get_account(conn, account_name)
    return build_sleeve_shadow_evaluation(
        conn,
        account=account,
        as_of_iso=as_of_iso,
        rolling_window_days=rolling_window_days,
    )


def main() -> int:
    args = parse_args()
    if int(args.rolling_window_days) < 1:
        print("--rolling-window-days must be >= 1", file=sys.stderr)
        return 1

    if not is_run_enabled(args):
        print(
            "Daily challenger shadow evaluation is disabled. "
            f"Use --enable-run or set {CHALLENGER_SHADOW_EVAL_ENABLED_ENV}=1 to execute.",
            file=sys.stderr,
        )
        return 0

    repo_root = Path(args.repo_root).expanduser().resolve()
    logs_dir = logs_dir_for_repo(repo_root)
    export_dir = repo_root / "local" / "exports" / "daily_challenger_shadow_eval"
    logs_dir.mkdir(parents=True, exist_ok=True)
    export_dir.mkdir(parents=True, exist_ok=True)

    now = dt.datetime.now()
    today = day_tag(now)
    timestamp = now.strftime("%Y%m%d_%H%M%S")
    log_path = logs_dir / f"daily_challenger_shadow_eval_{today}_{timestamp}.log"
    artifact_path = export_dir / f"daily_challenger_shadow_eval_{timestamp}.json"

    try:
        accounts = resolve_accounts(args.accounts, load_runtime_eligible_account_names())
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if not accounts:
        print("No accounts specified.", file=sys.stderr)
        return 1

    run_meta = {
        "job": "daily_challenger_shadow_eval",
        "run_source": args.run_source,
        "force_run": bool(args.force_run),
        "day_tag": today,
        "accounts": accounts,
        "rolling_window_days": int(args.rolling_window_days),
        "log_path": str(log_path.relative_to(repo_root)),
        "artifact_path": str(artifact_path.relative_to(repo_root)),
        "started_at": ts(),
    }
    tee_line(log_path, f"[{ts()}] RUN META: {json.dumps(run_meta, sort_keys=True)}")

    if not args.force_run and already_completed_today(logs_dir, today):
        message = "Daily challenger shadow evaluation already completed today; skipping duplicate run."
        tee_line(log_path, f"[{ts()}] SKIP: {message}")
        write_artifact(
            artifact_path,
            {
                **run_meta,
                "status": "skipped",
                "skip_reason": "already-completed-today",
                "results": [],
                "finished_at": ts(),
            },
        )
        print(message)
        return 0

    conn = ensure_db()
    try:
        results: list[dict[str, object]] = []
        as_of_iso = ts()
        for account_name in accounts:
            shadow_run = run_shadow_eval_for_account(
                conn,
                account_name=account_name,
                rolling_window_days=int(args.rolling_window_days),
                as_of_iso=as_of_iso,
            )
            serialized = _serialize_shadow_run(shadow_run)
            results.append(serialized)
            tee_line(
                log_path,
                (f"[{ts()}] SHADOW_EVAL: account={account_name} sleeves={len(shadow_run.sleeves)}"),
            )

        tee_line(log_path, f"[{ts()}] {COMPLETE_SENTINEL}")
        write_artifact(
            artifact_path,
            {
                **run_meta,
                "status": "success",
                "results": results,
                "finished_at": ts(),
            },
        )
        return 0
    except Exception as exc:
        tee_line(log_path, f"[{ts()}] ERROR: {exc}")
        write_artifact(
            artifact_path,
            {
                **run_meta,
                "status": "failed",
                "error": str(exc),
                "results": [],
                "finished_at": ts(),
            },
        )
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
