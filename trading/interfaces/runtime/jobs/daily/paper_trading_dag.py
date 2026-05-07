from __future__ import annotations

import datetime as dt
from collections.abc import Callable


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


def new_step_results() -> list[dict[str, object]]:
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


def step_result(step_results: list[dict[str, object]], step_id: str) -> dict[str, object]:
    for result in step_results:
        if result["step"] == step_id:
            return result
    raise ValueError(f"Unknown DAG step id: {step_id}")


def run_dag_step(
    step_results: list[dict[str, object]],
    *,
    step_id: str,
    run_fn: Callable[[], object],
    now_iso: Callable[[], str],
) -> dict[str, object]:
    result = step_result(step_results, step_id)
    start_time = dt.datetime.now(dt.timezone.utc)
    result["status"] = "running"
    result["started_at"] = now_iso()
    try:
        details = run_fn() or {}
    except Exception as exc:
        finish_time = dt.datetime.now(dt.timezone.utc)
        result["status"] = "failed"
        result["finished_at"] = now_iso()
        result["duration_seconds"] = round((finish_time - start_time).total_seconds(), 6)
        result["error"] = str(exc)
        if not isinstance(result["details"], dict):
            result["details"] = {}
        raise

    finish_time = dt.datetime.now(dt.timezone.utc)
    result["status"] = "ok"
    result["finished_at"] = now_iso()
    result["duration_seconds"] = round((finish_time - start_time).total_seconds(), 6)
    result["details"] = details if isinstance(details, dict) else {"value": details}
    return result


def skip_dag_step(
    step_results: list[dict[str, object]],
    *,
    step_id: str,
    reason: str,
    now_iso: Callable[[], str],
    details: dict[str, object] | None = None,
) -> dict[str, object]:
    result = step_result(step_results, step_id)
    now = now_iso()
    result["status"] = "skipped"
    result["started_at"] = now
    result["finished_at"] = now
    result["duration_seconds"] = 0.0
    payload = dict(details or {})
    payload["reason"] = reason
    result["details"] = payload
    return result


def completed_steps_from_dag(step_results: list[dict[str, object]]) -> list[dict[str, object]]:
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


def failed_step_id(step_results: list[dict[str, object]]) -> str | None:
    for step in step_results:
        if step["status"] == "failed":
            return str(step["step"])
    return None
