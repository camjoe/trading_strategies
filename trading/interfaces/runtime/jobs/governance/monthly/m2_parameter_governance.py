#!/usr/bin/env python3
"""M2 monthly governance job — active strategy parameter inventory for operator review."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from common.paths.repo_paths import get_repo_root
from infrastructure.database.init import ensure_db
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
from trading.interfaces.runtime.job_status import MONTHLY_GOVERNANCE_M2_PARAMETER_GOVERNANCE_COMPLETE_SENTINEL
from trading.repositories.sleeves import SleeveRepository
from trading.repositories.strategy_param_sets import StrategyParamSetRepository
from trading.services.accounts import load_runtime_eligible_account_names
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="M2 monthly governance: inventory active strategy parameters per sleeve.",
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
    return parser.parse_args()


def main() -> int:
    args = parse_args()

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
        account_results: list[dict[str, object]] = []
        for account_name in accounts:
            account = find_account(conn, account_name)
            if account is None:
                tee_line(log_path, f"[{ts()}] WARN: account not found in DB: {account_name}")
                continue

            sleeve_repo = SleeveRepository(conn)
            param_set_repo = StrategyParamSetRepository(conn)
            sleeves = sleeve_repo.fetch_for_account(account_id=account.id)
            sleeve_rows: list[dict[str, object]] = []

            for sleeve in sleeves:
                assignment = sleeve_repo.fetch_active_assignment(sleeve_id=sleeve.id)
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
                            except (ValueError, TypeError):
                                params = None

                sleeve_rows.append(
                    {
                        "sleeve_name": sleeve.name,
                        "strategy_name": strategy_name,
                        "param_set_id": param_set_id,
                        "params": params,
                    }
                )

            account_results.append({"account_name": account_name, "sleeves": sleeve_rows})
            tee_line(
                log_path,
                f"[{ts()}] PARAM_GOVERNANCE: account={account_name} sleeves={len(sleeve_rows)}",
            )

        payload: dict[str, object] = {
            "month": tag,
            "generated_at": ts(),
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
