#!/usr/bin/env python3
"""Run the daily paper-trading workflow with log + duplicate-run guard."""

from __future__ import annotations

import datetime as dt
import sys
import traceback
from pathlib import Path

from common.paths.repo_paths import get_repo_root
from trading.interfaces.runtime.job_status import (
    DAILY_PAPER_TRADING_COMPLETE_SENTINEL,
    DAILY_RUN_STATUS_FAILED,
    DAILY_RUN_STATUS_SUCCESS,
)
from trading.interfaces.runtime.jobs.daily.paper_trading.arguments import parse_args
from trading.interfaces.runtime.jobs.daily.paper_trading.caps import (
    group_accounts_by_caps,
)
from trading.interfaces.runtime.jobs.daily.paper_trading.dag import (
    DAILY_DAG_STEPS as _DAILY_DAG_STEPS,
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
)
from trading.interfaces.runtime.jobs.daily.paper_trading.run_context import (
    RunContextError,
    build_run_context,
)
from trading.interfaces.runtime.jobs.job_helpers import (
    CLI_MAIN_MODULE,
    DAILY_CHALLENGER_SHADOW_EVAL_MODULE,
    RUN_AUTO_TRADES_MODULE,
    latest_log_contains_sentinel,
    logs_dir_for_repo,
    resolve_email_config_from_env,
    stream_command,
    tee_line,
    ts,
    write_artifact,
)
from trading.interfaces.runtime.notifications import notify_runtime_event

REPO_ROOT = get_repo_root(__file__)
LOGS_DIR = logs_dir_for_repo(REPO_ROOT)


def _startup_log(message: str, logs_dir: Path = LOGS_DIR) -> None:
    log_path = logs_dir / f"daily_paper_trading_startup_{dt.date.today().strftime('%Y%m%d')}.log"
    timestamp = ts()
    try:
        logs_dir.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"[{timestamp}] {message}\n")
    except OSError:
        pass


try:
    from trading.services.accounts import load_runtime_eligible_account_names
except Exception as exc:
    _startup_log(f"IMPORT ERROR: {exc}")
    _startup_log(traceback.format_exc().rstrip())
    raise


COMPLETE_SENTINEL = DAILY_PAPER_TRADING_COMPLETE_SENTINEL
DAILY_DAG_STEPS = _DAILY_DAG_STEPS


def already_completed_today(log_dir: Path, *, today: dt.date | None = None) -> bool:
    today_tag = (today or dt.date.today()).strftime("%Y%m%d")
    return latest_log_contains_sentinel(
        log_dir,
        f"daily_paper_trading_{today_tag}_*.log",
        COMPLETE_SENTINEL,
    )


def run_auto_trader_group(
    log_path: Path,
    repo_root: Path,
    label: str,
    group_accounts: list[str],
    min_trades: int,
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
        "--min-trades",
        str(min_trades),
        "--max-trades",
        str(max_trades),
        "--fee",
        str(fee),
    ]
    if seed is not None:
        auto_trader_args.extend(["--seed", str(seed)])
    stream_command(log_path, label, auto_trader_args, repo_root)


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).expanduser().resolve()
    logs_dir = logs_dir_for_repo(repo_root)

    _startup_log(f"BOOT: script={__file__} cwd={Path.cwd()} python={sys.executable}", logs_dir)
    _startup_log("main() entered", logs_dir)
    logs_dir.mkdir(parents=True, exist_ok=True)

    if not args.force_run and already_completed_today(logs_dir):
        _startup_log(f"SKIP duplicate run (source={args.run_source})", logs_dir)
        print(f"Daily paper trading already completed today; skipping duplicate run. source={args.run_source}")
        return 0

    as_of_date: dt.date | None = None
    if args.as_of_date:
        try:
            as_of_date = dt.date.fromisoformat(args.as_of_date)
        except ValueError:
            print(f"Invalid --as-of-date value: {args.as_of_date!r}. Expected YYYY-MM-DD.", file=sys.stderr)
            return 1
        if not args.force_run and already_completed_today(logs_dir, today=as_of_date):
            _startup_log(f"SKIP duplicate run for as-of-date={as_of_date} (source={args.run_source})", logs_dir)
            print(f"Daily paper trading already completed for {as_of_date}; skipping. Use --force-run to override.")
            return 0

    all_accounts = load_runtime_eligible_account_names()
    try:
        context = build_run_context(
            args,
            all_accounts=all_accounts,
            as_of_date=as_of_date,
            repo_root=repo_root,
            logs_dir=logs_dir,
        )
    except RunContextError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    log_path = context.log_path
    artifact_path = context.artifact_path
    accounts = context.accounts
    account_trade_caps = context.account_trade_caps
    caps_summary = context.caps_summary
    run_meta = context.run_meta
    _startup_log(f"RUN log_path={log_path}", logs_dir)
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
        skip_dag_step(
            step_results,
            step_id="01_mark_book_nav",
            reason="nav_marking_is_handled_in_runtime_snapshot_and_reconciliation",
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
                key=lambda item: (item[0][0], item[0][1], item[1]),
            ):
                run_auto_trader_group(
                    log_path,
                    repo_root,
                    f"Auto Trader ({limits[0]}-{limits[1]} trades)",
                    group_accounts,
                    limits[0],
                    limits[1],
                    args.fee,
                    args.seed,
                )
                auto_trader_groups.append(
                    {
                        "accounts": group_accounts,
                        "min_trades": limits[0],
                        "max_trades": limits[1],
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
        skip_dag_step(
            step_results,
            step_id="06_pretrade_risk_gate",
            reason="risk_gate_runs_inside_auto_trading_runtime",
            now_iso=ts,
        )
        skip_dag_step(
            step_results,
            step_id="07_submit_ibkr_orders",
            reason="broker_submission_runs_inside_auto_trading_runtime",
            now_iso=ts,
        )

        snapshot_accounts: list[str] = []

        def _run_all_snapshots() -> dict[str, object]:
            for account in accounts:
                stream_command(
                    log_path,
                    f"Snapshot {account}",
                    ["-m", CLI_MAIN_MODULE, "snapshot", "--account", account],
                    repo_root,
                )
                snapshot_accounts.append(account)
            return {"accounts": snapshot_accounts, "count": len(snapshot_accounts)}

        run_dag_step(
            step_results,
            step_id="08_reconcile_fills_update_ledgers",
            run_fn=_run_all_snapshots,
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
