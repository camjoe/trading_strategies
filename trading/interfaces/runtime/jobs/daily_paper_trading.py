#!/usr/bin/env python3
"""Run the daily paper-trading workflow with log + duplicate-run guard."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import traceback
from pathlib import Path

from common.paths.repo_paths import get_repo_root
from trading.interfaces.runtime.jobs.job_helpers import CLI_MAIN_MODULE, DAILY_CHALLENGER_SHADOW_EVAL_MODULE, RUN_AUTO_TRADES_MODULE, RUNTIME_ALERT_WEBHOOK_ENV, latest_log_contains_sentinel, logs_dir_for_repo, resolve_accounts, stream_command, tee_line, ts, write_artifact
from trading.interfaces.runtime.notifications import notify_webhook_best_effort
from trading.interfaces.runtime.job_status import DAILY_PAPER_TRADING_COMPLETE_SENTINEL

REPO_ROOT = get_repo_root(__file__)
LOGS_DIR = logs_dir_for_repo(REPO_ROOT)
DEFAULT_TRADE_CAPS_CONFIG = REPO_ROOT / "trading" / "config" / "account_trade_caps.json"
SHADOW_EVAL_EXPORT_DIR = Path("local") / "exports" / "daily_challenger_shadow_eval"


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

DAILY_DAG_STEPS: tuple[tuple[str, str], ...] = (
    ("00_ingest_market_and_account", "Ingest market and account context"),
    ("01_mark_sleeve_nav", "Mark sleeve NAV"),
    ("02_run_signals_all_strategies", "Run incumbent/challenger strategy signals"),
    ("03_score_incumbent_vs_challengers", "Score incumbent versus challengers"),
    ("04_rotation_decision", "Apply rotation decision gates"),
    ("05_build_position_targets_by_sleeve", "Build position targets by sleeve"),
    ("06_pretrade_risk_gate", "Apply pretrade risk gate"),
    ("07_submit_ibkr_orders", "Submit broker orders"),
    ("08_reconcile_fills_update_ledgers", "Reconcile fills and update ledgers"),
    ("09_postclose_metrics_and_attribution", "Compute post-close metrics and attribution"),
    ("10_emit_report_and_alerts", "Emit report and alerts"),
)
TERMINAL_STEP_STATUSES = {"ok", "skipped", "failed"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the daily paper-trading workflow.")
    parser.add_argument(
        "--accounts",
        default="all",
        help="Comma-separated account names, or 'all' for every account in DB (default: all)",
    )
    parser.add_argument(
        "--primary-accounts",
        default="momentum_5k,meanrev_5k",
        help="Accounts that keep strict legacy limits (default: momentum_5k,meanrev_5k)",
    )
    parser.add_argument("--primary-min-trades", type=int, default=1)
    parser.add_argument("--primary-max-trades", type=int, default=5)
    parser.add_argument("--other-min-trades", type=int, default=1)
    parser.add_argument("--other-max-trades", type=int, default=11)
    parser.add_argument(
        "--account-trade-caps",
        default="",
        help=(
            "Optional per-account overrides in the form "
            "account:min-max,account:min-max (example: momentum_5k:1-5,core_growth_20k:1-8)"
        ),
    )
    parser.add_argument(
        "--trade-caps-config",
        default=DEFAULT_TRADE_CAPS_CONFIG,
        help=(
            "Path to JSON file with default and per-account trade caps "
            f"(default: {DEFAULT_TRADE_CAPS_CONFIG})"
        ),
    )
    parser.add_argument("--fee", type=float, default=0.0)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument(
        "--run-challenger-shadow-eval",
        action="store_true",
        help="Run challenger shadow evaluation before auto-trading.",
    )
    parser.add_argument(
        "--shadow-eval-rolling-window-days",
        type=int,
        default=30,
        help="Lookback window passed to challenger shadow evaluation (default: 30).",
    )
    parser.add_argument("--force-run", action="store_true", help="Allow duplicate same-day run")
    parser.add_argument("--run-source", default="scheduled-daily")
    parser.add_argument(
        "--notify-webhook-url",
        default=os.environ.get(RUNTIME_ALERT_WEBHOOK_ENV, ""),
        help=(
            "Optional webhook URL for runtime notifications "
            f"(default: ${RUNTIME_ALERT_WEBHOOK_ENV} if set)"
        ),
    )
    parser.add_argument(
        "--notify-on-success",
        action="store_true",
        help="Also send a webhook notification when the run completes successfully",
    )
    parser.add_argument(
        "--repo-root",
        default=str(REPO_ROOT),
        help="Repository root path (default: inferred from script location)",
    )
    return parser.parse_args()


def parse_account_trade_caps(value: str) -> dict[str, tuple[int, int]]:
    if not value.strip():
        return {}

    caps: dict[str, tuple[int, int]] = {}
    for raw_item in value.split(","):
        item = raw_item.strip()
        if not item:
            continue
        if ":" not in item or "-" not in item:
            raise ValueError(
                "--account-trade-caps entries must look like account:min-max"
            )
        account_name, raw_range = item.split(":", 1)
        min_text, max_text = raw_range.split("-", 1)
        caps[account_name.strip()] = _validate_trade_cap_range(
            account_name.strip(), int(min_text), int(max_text)
        )
    return caps


def _validate_trade_cap_range(name: str, min_trades: int, max_trades: int) -> tuple[int, int]:
    if min_trades < 1:
        raise ValueError(f"{name}: min trades must be >= 1")
    if max_trades < min_trades:
        raise ValueError(f"{name}: max trades must be >= min trades")
    return min_trades, max_trades


def load_trade_caps_config(config_path: Path) -> tuple[tuple[int, int] | None, dict[str, tuple[int, int]]]:
    if not config_path.exists():
        return None, {}

    raw = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Trade caps config must be a JSON object")

    default_caps: tuple[int, int] | None = None
    raw_default = raw.get("default")
    if raw_default is not None:
        if not isinstance(raw_default, dict) or "min" not in raw_default or "max" not in raw_default:
            raise ValueError("Trade caps config 'default' must contain min and max")
        default_caps = _validate_trade_cap_range(
            "default",
            int(raw_default["min"]),
            int(raw_default["max"]),
        )

    account_caps: dict[str, tuple[int, int]] = {}
    raw_accounts = raw.get("accounts", {})
    if not isinstance(raw_accounts, dict):
        raise ValueError("Trade caps config 'accounts' must be an object")

    for account_name, caps in raw_accounts.items():
        if not isinstance(caps, dict) or "min" not in caps or "max" not in caps:
            raise ValueError(f"Trade caps config for account '{account_name}' must contain min and max")
        account_caps[account_name] = _validate_trade_cap_range(
            account_name,
            int(caps["min"]),
            int(caps["max"]),
        )

    return default_caps, account_caps


def resolve_trade_caps(
    accounts: list[str],
    configured_default_caps: tuple[int, int] | None,
    configured_account_caps: dict[str, tuple[int, int]],
    primary_accounts: set[str],
    primary_min_trades: int,
    primary_max_trades: int,
    other_min_trades: int,
    other_max_trades: int,
    account_trade_cap_overrides: dict[str, tuple[int, int]],
) -> dict[str, tuple[int, int]]:
    resolved: dict[str, tuple[int, int]] = {}
    for account in accounts:
        if account in account_trade_cap_overrides:
            resolved[account] = account_trade_cap_overrides[account]
            continue
        if account in configured_account_caps:
            resolved[account] = configured_account_caps[account]
            continue
        if configured_default_caps is not None:
            resolved[account] = configured_default_caps
            continue
        if account in primary_accounts:
            resolved[account] = (primary_min_trades, primary_max_trades)
        else:
            resolved[account] = (other_min_trades, other_max_trades)
    return resolved


def already_completed_today(log_dir: Path, *, today: dt.date | None = None) -> bool:
    today_tag = (today or dt.date.today()).strftime("%Y%m%d")
    return latest_log_contains_sentinel(
        log_dir,
        f"daily_paper_trading_{today_tag}_*.log",
        COMPLETE_SENTINEL,
    )


def group_accounts_by_caps(
    accounts: list[str],
    caps: dict[str, tuple[int, int]],
) -> dict[tuple[int, int], list[str]]:
    grouped: dict[tuple[int, int], list[str]] = {}
    for account in accounts:
        grouped.setdefault(caps[account], []).append(account)
    return grouped


def _latest_shadow_eval_summary(repo_root: Path) -> dict[str, object] | None:
    export_dir = repo_root / SHADOW_EVAL_EXPORT_DIR
    artifacts = sorted(
        export_dir.glob("daily_challenger_shadow_eval_*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not artifacts:
        return None
    latest = artifacts[0]
    payload = json.loads(latest.read_text(encoding="utf-8"))
    results = payload.get("results", [])
    if not isinstance(results, list):
        results = []
    sleeve_count = 0
    challenger_count = 0
    for account_result in results:
        if not isinstance(account_result, dict):
            continue
        sleeves = account_result.get("sleeves", [])
        if not isinstance(sleeves, list):
            continue
        sleeve_count += len(sleeves)
        for sleeve in sleeves:
            if not isinstance(sleeve, dict):
                continue
            challenger_count += int(sleeve.get("challenger_count") or 0)
    return {
        "status": payload.get("status"),
        "artifact_path": str(latest.relative_to(repo_root)),
        "account_count": len(results),
        "sleeve_count": sleeve_count,
        "challenger_count": challenger_count,
    }


def _new_step_results() -> list[dict[str, object]]:
    return [
        {
            "step": step_id,
            "name": step_name,
            "status": "pending",
            "started_at": None,
            "finished_at": None,
            "duration_seconds": None,
            "details": {},
            "error": None,
        }
        for step_id, step_name in DAILY_DAG_STEPS
    ]


def _step_result(step_results: list[dict[str, object]], step_id: str) -> dict[str, object]:
    for result in step_results:
        if result["step"] == step_id:
            return result
    raise ValueError(f"Unknown DAG step id: {step_id}")


def _run_dag_step(
    step_results: list[dict[str, object]],
    *,
    step_id: str,
    run_fn,
) -> dict[str, object]:
    result = _step_result(step_results, step_id)
    start_time = dt.datetime.now(dt.timezone.utc)
    result["status"] = "running"
    result["started_at"] = ts()
    try:
        details = run_fn() or {}
    except Exception as exc:
        finish_time = dt.datetime.now(dt.timezone.utc)
        result["status"] = "failed"
        result["finished_at"] = ts()
        result["duration_seconds"] = round((finish_time - start_time).total_seconds(), 6)
        result["error"] = str(exc)
        if not isinstance(result["details"], dict):
            result["details"] = {}
        raise

    finish_time = dt.datetime.now(dt.timezone.utc)
    result["status"] = "ok"
    result["finished_at"] = ts()
    result["duration_seconds"] = round((finish_time - start_time).total_seconds(), 6)
    result["details"] = details if isinstance(details, dict) else {"value": details}
    return result


def _skip_dag_step(
    step_results: list[dict[str, object]],
    *,
    step_id: str,
    reason: str,
    details: dict[str, object] | None = None,
) -> dict[str, object]:
    result = _step_result(step_results, step_id)
    now = ts()
    result["status"] = "skipped"
    result["started_at"] = now
    result["finished_at"] = now
    result["duration_seconds"] = 0.0
    payload = dict(details or {})
    payload["reason"] = reason
    result["details"] = payload
    return result


def _completed_steps_from_dag(step_results: list[dict[str, object]]) -> list[dict[str, object]]:
    completed: list[dict[str, object]] = []
    for step in step_results:
        status = str(step["status"])
        if status not in TERMINAL_STEP_STATUSES:
            continue
        completed.append(
            {
                "step": step["step"],
                "status": status,
                "details": step["details"],
            }
        )
    return completed


def _failed_step_id(step_results: list[dict[str, object]]) -> str | None:
    for step in step_results:
        if step["status"] == "failed":
            return str(step["step"])
    return None


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


def _maybe_send_notification(
    *,
    webhook_url: str,
    notify_on_success: bool,
    status: str,
    message: str,
    details: dict[str, object],
) -> None:
    if status == "ok" and not notify_on_success:
        return
    notify_webhook_best_effort(
        webhook_url=webhook_url,
        event="daily-paper-trading",
        status=status,
        message=message,
        details=details,
    )


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

    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = logs_dir / f"daily_paper_trading_{timestamp}.log"
    artifact_path = repo_root / "local" / "exports" / "daily_paper_trading" / f"daily_paper_trading_{timestamp}.json"
    _startup_log(f"RUN log_path={log_path}", logs_dir)

    all_accounts = load_runtime_eligible_account_names()
    try:
        accounts = resolve_accounts(args.accounts, all_accounts)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if not accounts:
        print("No accounts specified.", file=sys.stderr)
        return 1

    if args.primary_min_trades < 1:
        print("--primary-min-trades must be >= 1", file=sys.stderr)
        return 1
    if args.shadow_eval_rolling_window_days < 1:
        print("--shadow-eval-rolling-window-days must be >= 1", file=sys.stderr)
        return 1
    if args.primary_max_trades < args.primary_min_trades:
        print("--primary-max-trades must be >= --primary-min-trades", file=sys.stderr)
        return 1
    if args.other_min_trades < 1:
        print("--other-min-trades must be >= 1", file=sys.stderr)
        return 1
    if args.other_max_trades < args.other_min_trades:
        print("--other-max-trades must be >= --other-min-trades", file=sys.stderr)
        return 1

    primary_accounts = {item.strip() for item in args.primary_accounts.split(",") if item.strip()}
    caps_config_path = Path(args.trade_caps_config)
    if not caps_config_path.is_absolute():
        caps_config_path = repo_root / caps_config_path

    try:
        configured_default_caps, configured_account_caps = load_trade_caps_config(caps_config_path)
    except ValueError as exc:
        print(f"Invalid trade caps config: {exc}", file=sys.stderr)
        return 1

    try:
        account_trade_cap_overrides = parse_account_trade_caps(args.account_trade_caps)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    known_accounts = set(all_accounts)
    unknown_override_accounts = [name for name in account_trade_cap_overrides if name not in known_accounts]
    if unknown_override_accounts:
        print(
            f"Unknown account(s) in --account-trade-caps: {', '.join(unknown_override_accounts)}",
            file=sys.stderr,
        )
        return 1

    account_trade_caps = resolve_trade_caps(
        accounts,
        configured_default_caps,
        configured_account_caps,
        primary_accounts,
        args.primary_min_trades,
        args.primary_max_trades,
        args.other_min_trades,
        args.other_max_trades,
        account_trade_cap_overrides,
    )
    caps_summary = ",".join(
        f"{name}:{limits[0]}-{limits[1]}" for name, limits in account_trade_caps.items()
    )

    tee_line(
        log_path,
        f"[{ts()}] RUN META: "
        f"source={args.run_source} force={bool(args.force_run)} "
        f"accounts={','.join(accounts)} caps={caps_summary}",
    )
    run_meta = {
        "job": "daily_paper_trading",
        "run_source": args.run_source,
        "force_run": bool(args.force_run),
        "accounts": accounts,
        "account_count": len(accounts),
        "caps_summary": caps_summary,
        "log_path": str(log_path.relative_to(repo_root)),
        "artifact_path": str(artifact_path.relative_to(repo_root)),
        "started_at": ts(),
    }
    step_results = _new_step_results()

    try:
        _run_dag_step(
            step_results,
            step_id="00_ingest_market_and_account",
            run_fn=lambda: {
                "accounts": accounts,
                "account_count": len(accounts),
                "caps_summary": caps_summary,
            },
        )
        _skip_dag_step(
            step_results,
            step_id="01_mark_sleeve_nav",
            reason="nav_marking_is_handled_in_runtime_snapshot_and_reconciliation",
        )

        shadow_eval_summary: dict[str, object] | None = None
        if args.run_challenger_shadow_eval:
            _run_dag_step(
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
                            "--rolling-window-days",
                            str(args.shadow_eval_rolling_window_days),
                            "--run-source",
                            "daily-paper-trading",
                        ],
                        repo_root,
                    ),
                    {"rolling_window_days": args.shadow_eval_rolling_window_days},
                )[1],
            )
            shadow_eval_summary = _latest_shadow_eval_summary(repo_root)
            _run_dag_step(
                step_results,
                step_id="03_score_incumbent_vs_challengers",
                run_fn=lambda: {"shadow_eval_summary": shadow_eval_summary},
            )
        else:
            _skip_dag_step(
                step_results,
                step_id="02_run_signals_all_strategies",
                reason="challenger_shadow_eval_not_enabled",
            )
            _skip_dag_step(
                step_results,
                step_id="03_score_incumbent_vs_challengers",
                reason="no_challenger_signal_run",
            )

        _skip_dag_step(
            step_results,
            step_id="04_rotation_decision",
            reason="rotation_decisions_are_enforced_inside_sleeve_runtime_path",
        )

        grouped_accounts = group_accounts_by_caps(accounts, account_trade_caps)
        auto_trader_groups: list[dict[str, object]] = []
        _run_dag_step(
            step_results,
            step_id="05_build_position_targets_by_sleeve",
            run_fn=lambda: (
                [
                    (
                        run_auto_trader_group(
                            log_path,
                            repo_root,
                            f"Auto Trader ({limits[0]}-{limits[1]} trades)",
                            group_accounts,
                            limits[0],
                            limits[1],
                            args.fee,
                            args.seed,
                        ),
                        auto_trader_groups.append(
                            {
                                "accounts": group_accounts,
                                "min_trades": limits[0],
                                "max_trades": limits[1],
                            }
                        ),
                    )
                    for limits, group_accounts in sorted(
                        grouped_accounts.items(),
                        key=lambda item: (item[0][0], item[0][1], item[1]),
                    )
                ],
                {
                    "groups": auto_trader_groups,
                    "group_count": len(auto_trader_groups),
                    "shadow_eval_summary": shadow_eval_summary,
                },
            )[1],
        )
        _skip_dag_step(
            step_results,
            step_id="06_pretrade_risk_gate",
            reason="risk_gate_runs_inside_auto_trading_runtime",
        )
        _skip_dag_step(
            step_results,
            step_id="07_submit_ibkr_orders",
            reason="broker_submission_runs_inside_auto_trading_runtime",
        )

        snapshot_accounts: list[str] = []
        _run_dag_step(
            step_results,
            step_id="08_reconcile_fills_update_ledgers",
            run_fn=lambda: (
                [
                    (
                        stream_command(
                            log_path,
                            f"Snapshot {account}",
                            ["-m", CLI_MAIN_MODULE, "snapshot", "--account", account],
                            repo_root,
                        ),
                        snapshot_accounts.append(account),
                    )
                    for account in accounts
                ],
                {"accounts": snapshot_accounts, "count": len(snapshot_accounts)},
            )[1],
        )

        _run_dag_step(
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
        )

        _run_dag_step(
            step_results,
            step_id="10_emit_report_and_alerts",
            run_fn=lambda: {
                "artifact_path": str(artifact_path.relative_to(repo_root)),
                "notify_on_success": bool(args.notify_on_success),
            },
        )

        completed_steps = _completed_steps_from_dag(step_results)
        tee_line(log_path, f"[{ts()}] {COMPLETE_SENTINEL}")
        success_payload = {
            **run_meta,
            "status": "success",
            "completed_steps": completed_steps,
            "step_results": step_results,
            "finished_at": ts(),
        }
        write_artifact(
            artifact_path,
            success_payload,
        )
        _maybe_send_notification(
            webhook_url=args.notify_webhook_url,
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
            "status": "failed",
            "completed_steps": _completed_steps_from_dag(step_results),
            "step_results": step_results,
            "failed_step": _failed_step_id(step_results),
            "error": str(exc),
            "finished_at": ts(),
        }
        write_artifact(
            artifact_path,
            failure_payload,
        )
        _maybe_send_notification(
            webhook_url=args.notify_webhook_url,
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


if __name__ == "__main__":
    raise SystemExit(main())
