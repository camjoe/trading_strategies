#!/usr/bin/env python3
"""Run daily challenger shadow evaluation and write account-level artifacts."""

from __future__ import annotations

import argparse

from trading.interfaces.runtime.jobs.job_helpers import ts
from trading.interfaces.runtime.jobs.job_runner import JobContext, daily_account_job
from trading.interfaces.runtime.job_status import (
    DAILY_CHALLENGER_SHADOW_EVAL_COMPLETE_SENTINEL,
)
from trading.services.accounts import get_account
from trading.services.sleeves.shadow_evaluation import (
    DEFAULT_SHADOW_ROLLING_WINDOW_DAYS,
    ShadowEvaluationRun,
    build_sleeve_shadow_evaluation,
)

JOB_NAME = "daily_challenger_shadow_eval"
COMPLETE_SENTINEL = DAILY_CHALLENGER_SHADOW_EVAL_COMPLETE_SENTINEL

# Explicit opt-in env var so shadow evaluation runs remain operator-controlled.
CHALLENGER_SHADOW_EVAL_ENABLED_ENV = "DAILY_CHALLENGER_SHADOW_EVAL_ENABLED"


def _add_window_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--rolling-window-days",
        type=int,
        default=DEFAULT_SHADOW_ROLLING_WINDOW_DAYS,
        help=(
            "Historical lookback window in days for challenger evidence "
            f"(default: {DEFAULT_SHADOW_ROLLING_WINDOW_DAYS})"
        ),
    )


def _validate(args: argparse.Namespace) -> str | None:
    if int(args.rolling_window_days) < 1:
        return "--rolling-window-days must be >= 1"
    return None


def _run_meta(args: argparse.Namespace) -> dict[str, object]:
    return {"rolling_window_days": int(args.rolling_window_days)}


def _serialize_shadow_run(result: ShadowEvaluationRun) -> dict[str, object]:
    return {
        "account_id": result.account_id,
        "account_name": result.account_name,
        "window_start_day": result.window_start_day,
        "window_end_day": result.window_end_day,
        "sleeves": [
            {
                "book_id": sleeve.book_id,
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


@daily_account_job(
    job_name=JOB_NAME,
    sentinel=COMPLETE_SENTINEL,
    description="Run daily challenger shadow evaluation for runtime-eligible accounts.",
    enabled_env=CHALLENGER_SHADOW_EVAL_ENABLED_ENV,
    disabled_message=(
        "Daily challenger shadow evaluation is disabled. "
        "Use --enable-run or set DAILY_CHALLENGER_SHADOW_EVAL_ENABLED=1 to execute."
    ),
    run_source_default="daily-challenger-shadow-eval",
    export_subdir="daily_challenger_shadow_eval",
    label="Challenger shadow evaluation",
    open_db=True,
    add_arguments=_add_window_arg,
    validate=_validate,
    extra_meta=_run_meta,
)
def main(ctx: JobContext, account: str) -> dict[str, object]:
    shadow_run = run_shadow_eval_for_account(
        ctx.conn,
        account_name=account,
        rolling_window_days=int(ctx.args.rolling_window_days),
        as_of_iso=ts(),
    )
    ctx.log(f"SHADOW_EVAL: account={account} sleeves={len(shadow_run.sleeves)}")
    return {"status": "success", **_serialize_shadow_run(shadow_run)}


if __name__ == "__main__":
    raise SystemExit(main())
