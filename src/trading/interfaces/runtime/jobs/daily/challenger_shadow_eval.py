#!/usr/bin/env python3
"""Run daily challenger shadow evaluation and write account-level artifacts."""

from __future__ import annotations

import argparse
from collections.abc import Callable

from infrastructure.feature_providers.policy_provider import PolicyFeatureProvider
from trading.domain.feature_provider import ExternalFeatureBundle
from trading.interfaces.runtime.job_status import (
    DAILY_CHALLENGER_SHADOW_EVAL_COMPLETE_SENTINEL,
)
from trading.interfaces.runtime.jobs.job_helpers import ts
from trading.interfaces.runtime.jobs.job_runner import JobContext, daily_account_job
from trading.services.accounts import get_account
from trading.services.books.rotation.challenger_evaluation import (
    ChallengerEvaluationRun,
    build_book_challenger_evaluations,
)

JOB_NAME = "daily_challenger_shadow_eval"
COMPLETE_SENTINEL = DAILY_CHALLENGER_SHADOW_EVAL_COMPLETE_SENTINEL

# Explicit opt-in env var so shadow evaluation runs remain operator-controlled.
CHALLENGER_SHADOW_EVAL_ENABLED_ENV = "DAILY_CHALLENGER_SHADOW_EVAL_ENABLED"

# Composition root: one provider shared across every account this job processes in
# one run (the job runner calls `main` once per account; the ETF regime read is
# account-agnostic, so a shared instance also gets the provider's own cache instead
# of re-hitting yfinance once per account).
_policy_provider = PolicyFeatureProvider()


def _add_window_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--rolling-window-days",
        type=int,
        default=None,
        help=(
            "Override the historical lookback window in days for challenger"
            " evidence (default: each book's own configured lookback)"
        ),
    )


def _validate(args: argparse.Namespace) -> str | None:
    if args.rolling_window_days is not None and int(args.rolling_window_days) < 1:
        return "--rolling-window-days must be >= 1"
    return None


def _run_meta(args: argparse.Namespace) -> dict[str, object]:
    window = args.rolling_window_days
    return {"rolling_window_days": int(window) if window is not None else "book-owned"}


def _serialize_shadow_run(result: ChallengerEvaluationRun) -> dict[str, object]:
    return {
        "account_id": result.account_id,
        "account_name": result.account_name,
        "books": [
            {
                "book_id": book.book_id,
                "incumbent_strategy": book.incumbent_strategy,
                # The evidence window is per-book (book-owned lookback, ADR 014).
                "rolling_window_days": book.rolling_window_days,
                "window_start_day": book.window_start_day,
                "window_end_day": book.window_end_day,
                "challenger_count": len(book.challengers),
                "challengers": [
                    {
                        "strategy_name": challenger.strategy_name,
                        "trade_count": challenger.trade_count,
                        "risk_adjusted_return": challenger.risk_adjusted_return,
                        "stability": challenger.stability,
                        "drawdown_penalty": challenger.drawdown_penalty,
                        "regime_fit": challenger.regime_fit,
                    }
                    for challenger in book.challengers
                ],
            }
            for book in result.books
        ],
    }


def run_shadow_eval_for_account(
    conn,
    *,
    account_name: str,
    rolling_window_days: int | None,
    as_of_iso: str,
    fetch_regime: Callable[[str], ExternalFeatureBundle] | None = None,
) -> ChallengerEvaluationRun:
    account = get_account(conn, account_name)
    return build_book_challenger_evaluations(
        conn,
        account=account,
        as_of_iso=as_of_iso,
        rolling_window_days=rolling_window_days,
        fetch_regime=fetch_regime,
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
    window = ctx.args.rolling_window_days
    shadow_run = run_shadow_eval_for_account(
        ctx.conn,
        account_name=account,
        rolling_window_days=int(window) if window is not None else None,
        as_of_iso=ts(),
        fetch_regime=_policy_provider.get_features,
    )
    ctx.log(f"SHADOW_EVAL: account={account} books={len(shadow_run.books)}")
    return {"status": "success", **_serialize_shadow_run(shadow_run)}


if __name__ == "__main__":
    raise SystemExit(main())
