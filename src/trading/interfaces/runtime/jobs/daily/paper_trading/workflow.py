"""DAG orchestration for the daily paper-trading workflow.

``run_workflow`` executes the daily run's step DAG against a resolved
``DailyRunContext``: optional challenger shadow-eval, the auto-trader groups,
snapshots, post-close metrics, and the operator report — then writes the run
artifact and sends notifications. It owns the success/failure boundary and
returns the process exit code.
"""

from __future__ import annotations

import argparse
import time
from collections.abc import Callable
from pathlib import Path

from trading.interfaces.runtime.job_status import (
    DAILY_PAPER_TRADING_COMPLETE_SENTINEL,
    DAILY_RUN_STATUS_FAILED,
    DAILY_RUN_STATUS_SUCCESS,
)
from trading.interfaces.runtime.jobs.daily.paper_trading.caps import group_accounts_by_caps
from trading.interfaces.runtime.jobs.daily.paper_trading.dag import (
    completed_steps_from_dag,
    failed_step_id,
    new_step_results,
    run_dag_step,
    serialize_step_results,
    skip_dag_step,
)
from trading.interfaces.runtime.jobs.daily.paper_trading.reporting import (
    build_daily_operator_report as _build_daily_operator_report,
    latest_shadow_eval_summary,
    maybe_send_notification,
    risk_gate_step_result as _risk_gate_step_result,
    submission_step_result as _submission_step_result,
)
from trading.interfaces.runtime.jobs.daily.paper_trading.run_context import DailyRunContext
from trading.interfaces.runtime.jobs.job_helpers import (
    CLI_MAIN_MODULE,
    DAILY_CHALLENGER_SHADOW_EVAL_MODULE,
    RECONCILE_ORDERS_MODULE,
    RUN_AUTO_TRADES_MODULE,
    resolve_email_config_from_env,
    stream_command,
    tee_line,
    ts,
    write_artifact,
)
from trading.interfaces.runtime.notifications import notify_runtime_event

COMPLETE_SENTINEL = DAILY_PAPER_TRADING_COMPLETE_SENTINEL

# Snapshot attempts per account before the step fails. Snapshots reach market data
# and the DB, which fail transiently far more often than permanently, and the
# pre-submit gate refuses to trade without a fresh snapshot — so a flaky read
# should cost a retry rather than the whole run.
SNAPSHOT_MAX_ATTEMPTS = 3
# Base delay for exponential backoff between snapshot attempts, in seconds.
SNAPSHOT_BACKOFF_SECONDS = 2.0


def run_auto_trader_group(
    log_path: Path,
    repo_root: Path,
    label: str,
    group_accounts: list[str],
    max_trades: int,
    fee: float,
    seed: int | None,
) -> None:
    if not group_accounts:
        return
    auto_trader_args = [
        "-m",
        RUN_AUTO_TRADES_MODULE,
        "--accounts",
        ",".join(group_accounts),
        "--max-trades",
        str(max_trades),
        "--fee",
        str(fee),
    ]
    if seed is not None:
        auto_trader_args.extend(["--seed", str(seed)])
    stream_command(log_path, label, auto_trader_args, repo_root)


def snapshot_account_with_retry(
    log_path: Path,
    repo_root: Path,
    account: str,
    label: str,
    *,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> None:
    """Snapshot one account, retrying transient failures with backoff.

    Every failure is treated as retryable — a snapshot has no failure mode worth
    distinguishing here, it either recorded equity or it did not. Re-raises the
    last error once ``SNAPSHOT_MAX_ATTEMPTS`` is exhausted.
    """
    for attempt in range(1, SNAPSHOT_MAX_ATTEMPTS + 1):
        try:
            stream_command(
                log_path,
                f"{label} snapshot {account}",
                ["-m", CLI_MAIN_MODULE, "snapshot", "--account", account],
                repo_root,
            )
            return
        except Exception as exc:
            if attempt == SNAPSHOT_MAX_ATTEMPTS:
                raise
            tee_line(
                log_path,
                f"[{ts()}] RETRY: {label} snapshot {account} attempt {attempt}/{SNAPSHOT_MAX_ATTEMPTS} failed: {exc}",
            )
            sleep_fn(SNAPSHOT_BACKOFF_SECONDS * (2 ** (attempt - 1)))


def reconcile_and_snapshot(
    log_path: Path,
    repo_root: Path,
    accounts: list[str],
    label: str,
) -> dict[str, object]:
    """Apply outstanding broker fills, then snapshot every account.

    Reconciliation comes first so the snapshot records equity that already
    accounts for fills the broker reported since the last pass — a no-op for
    paper accounts, load-bearing for the async socket path. *label* separates the
    pre- and post-trade passes in the log.

    Snapshots retry on transient failure; an account that still fails after
    ``SNAPSHOT_MAX_ATTEMPTS`` propagates, failing the step.
    """
    stream_command(
        log_path,
        f"{label} reconcile fills",
        ["-m", RECONCILE_ORDERS_MODULE, "--accounts", ",".join(accounts)],
        repo_root,
    )
    for account in accounts:
        snapshot_account_with_retry(log_path, repo_root, account, label)
    return {"accounts": list(accounts), "count": len(accounts)}


def run_workflow(args: argparse.Namespace, context: DailyRunContext) -> int:
    repo_root = context.repo_root
    log_path = context.log_path
    artifact_path = context.artifact_path
    accounts = context.accounts
    account_trade_caps = context.account_trade_caps
    caps_summary = context.caps_summary
    run_meta = context.run_meta
    step_results = new_step_results()

    try:
        run_dag_step(
            step_results,
            step_id="00_ingest_market_and_account",
            run_fn=lambda: {
                "accounts": accounts,
                "account_count": len(accounts),
                "caps_summary": caps_summary,
            },
            now_iso=ts,
        )
        # The pre-submit gate reconciles book equity against the latest equity
        # snapshot and kills the run when that snapshot is missing or older than
        # MAX_RECONCILIATION_SNAPSHOT_AGE_SECONDS. Snapshotting here — before any
        # trading — is what lets the run stand on its own at any point the market
        # is open; the post-trade pass at step 08 still records end-state equity.
        run_dag_step(
            step_results,
            step_id="01_mark_book_nav",
            run_fn=lambda: reconcile_and_snapshot(log_path, repo_root, accounts, "Pre-trade"),
            now_iso=ts,
        )

        shadow_eval_summary: dict[str, object] | None = None
        if args.run_challenger_shadow_eval:
            # An explicit window overrides every book's own lookback (ADR 014),
            # so the flag is only forwarded when the operator set one.
            shadow_eval_window_args = (
                ["--rolling-window-days", str(args.shadow_eval_rolling_window_days)]
                if args.shadow_eval_rolling_window_days is not None
                else []
            )
            run_dag_step(
                step_results,
                step_id="02_run_signals_all_strategies",
                run_fn=lambda: (
                    stream_command(
                        log_path,
                        "Challenger Shadow Eval",
                        [
                            "-m",
                            DAILY_CHALLENGER_SHADOW_EVAL_MODULE,
                            "--accounts",
                            ",".join(accounts),
                            "--enable-run",
                            *shadow_eval_window_args,
                            "--run-source",
                            "daily-paper-trading",
                        ],
                        repo_root,
                    ),
                    {
                        "rolling_window_days": (
                            args.shadow_eval_rolling_window_days
                            if args.shadow_eval_rolling_window_days is not None
                            else "book-owned"
                        )
                    },
                )[1],
                now_iso=ts,
            )
            shadow_eval_summary = latest_shadow_eval_summary(repo_root)
            run_dag_step(
                step_results,
                step_id="03_score_incumbent_vs_challengers",
                run_fn=lambda: {"shadow_eval_summary": shadow_eval_summary},
                now_iso=ts,
            )
        else:
            skip_dag_step(
                step_results,
                step_id="02_run_signals_all_strategies",
                reason="challenger_shadow_eval_not_enabled",
                now_iso=ts,
            )
            skip_dag_step(
                step_results,
                step_id="03_score_incumbent_vs_challengers",
                reason="no_challenger_signal_run",
                now_iso=ts,
            )

        skip_dag_step(
            step_results,
            step_id="04_rotation_decision",
            reason="rotation_decisions_are_enforced_inside_book_runtime_path",
            now_iso=ts,
        )

        grouped_accounts = group_accounts_by_caps(accounts, account_trade_caps)
        auto_trader_groups: list[dict[str, object]] = []

        def _run_all_auto_trader_groups() -> dict[str, object]:
            for limits, group_accounts in sorted(
                grouped_accounts.items(),
                key=lambda item: (item[0], item[1]),
            ):
                run_auto_trader_group(
                    log_path,
                    repo_root,
                    f"Auto Trader (up to {limits} trades)",
                    group_accounts,
                    limits,
                    args.fee,
                    args.seed,
                )
                auto_trader_groups.append(
                    {
                        "accounts": group_accounts,
                        "max_trades": limits,
                    }
                )
            return {
                "groups": auto_trader_groups,
                "group_count": len(auto_trader_groups),
                "shadow_eval_summary": shadow_eval_summary,
            }

        run_dag_step(
            step_results,
            step_id="05_build_position_targets_by_book",
            run_fn=_run_all_auto_trader_groups,
            now_iso=ts,
        )
        # The gate and the submission both run inside the auto-trading runtime at
        # step 05. These steps report on the rows that work left behind, so a run
        # artifact says what was blocked and what actually reached the broker
        # instead of going quiet at the point that matters most.
        run_dag_step(
            step_results,
            step_id="06_pretrade_risk_gate",
            run_fn=lambda: _risk_gate_step_result(accounts),
            now_iso=ts,
        )
        run_dag_step(
            step_results,
            step_id="07_submit_ibkr_orders",
            run_fn=lambda: _submission_step_result(accounts),
            now_iso=ts,
        )

        run_dag_step(
            step_results,
            step_id="08_reconcile_fills_update_ledgers",
            run_fn=lambda: reconcile_and_snapshot(log_path, repo_root, accounts, "Post-trade"),
            now_iso=ts,
        )

        run_dag_step(
            step_results,
            step_id="09_postclose_metrics_and_attribution",
            run_fn=lambda: (
                stream_command(
                    log_path,
                    "Compare Strategies",
                    ["-m", CLI_MAIN_MODULE, "compare-strategies"],
                    repo_root,
                ),
                {"command": "compare-strategies"},
            )[1],
            now_iso=ts,
        )

        run_dag_step(
            step_results,
            step_id="10_emit_report_and_alerts",
            run_fn=lambda: _build_daily_operator_report(
                accounts,
                artifact_path,
                repo_root,
                bool(args.notify_on_success),
            ),
            now_iso=ts,
        )

        tee_line(log_path, f"[{ts()}] {COMPLETE_SENTINEL}")
        success_payload = {
            **run_meta,
            "status": DAILY_RUN_STATUS_SUCCESS,
            "completed_steps": completed_steps_from_dag(step_results),
            "step_results": serialize_step_results(step_results),
            "finished_at": ts(),
        }
        write_artifact(
            artifact_path,
            success_payload,
        )
        maybe_send_notification(
            notifier=notify_runtime_event,
            webhook_url=args.notify_webhook_url,
            email_config=resolve_email_config_from_env(),
            notify_on_success=args.notify_on_success,
            status="ok",
            message="Daily paper trading run completed successfully",
            details={
                "accounts": accounts,
                "account_count": len(accounts),
                "log_path": str(log_path),
                "run_source": args.run_source,
            },
        )
        return 0
    except Exception as exc:
        tee_line(log_path, f"[{ts()}] ERROR: {exc}")
        failure_payload = {
            **run_meta,
            "status": DAILY_RUN_STATUS_FAILED,
            "completed_steps": completed_steps_from_dag(step_results),
            "step_results": serialize_step_results(step_results),
            "failed_step": failed_step_id(step_results),
            "error": str(exc),
            "finished_at": ts(),
        }
        write_artifact(
            artifact_path,
            failure_payload,
        )
        maybe_send_notification(
            notifier=notify_runtime_event,
            webhook_url=args.notify_webhook_url,
            email_config=resolve_email_config_from_env(),
            notify_on_success=args.notify_on_success,
            status="fail",
            message=f"Daily paper trading run failed: {exc}",
            details={
                "accounts": accounts,
                "account_count": len(accounts),
                "log_path": str(log_path),
                "run_source": args.run_source,
            },
        )
        return 1
