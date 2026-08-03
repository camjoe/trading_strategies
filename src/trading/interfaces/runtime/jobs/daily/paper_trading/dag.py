from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass, field

from common.runtime_job_status import TERMINAL_STEP_STATUSES

# Step *ids* are a persisted contract — they appear in every historical run
# artifact and `maintenance/replay_daily_runs` reads those — so they stay fixed
# even where they no longer describe the work. The display names are the honest
# ones; read them, not the ids.
#
# Where the trading controls actually live: step 05 runs the whole trading path
# (rotation, pre-submit risk gate, broker submission) in one subprocess. Steps 06
# and 07 do not gate or submit anything — they summarize rows step 05 already
# wrote. Step 04 never runs; rotation is enforced inside the step 05 runtime.
DAILY_DAG_STEPS: tuple[tuple[str, str], ...] = (
    ("00_ingest_market_and_account", "Resolve run context (accounts and trade caps)"),
    ("01_mark_book_nav", "Reconcile fills and snapshot equity (pre-trade)"),
    ("02_run_signals_all_strategies", "Run challenger shadow evaluation"),
    ("03_score_incumbent_vs_challengers", "Record shadow-evaluation summary"),
    ("04_rotation_decision", "Rotation decision (applied inside the step 05 runtime)"),
    ("05_build_position_targets_by_book", "Run trading books: rotation, risk gate, submission"),
    ("06_pretrade_risk_gate", "Report pretrade risk-gate decisions from this run"),
    ("07_submit_ibkr_orders", "Report broker submissions from this run"),
    ("08_reconcile_fills_update_ledgers", "Reconcile fills and snapshot equity (post-trade)"),
    ("09_postclose_metrics_and_attribution", "Compare strategies (post-close)"),
    ("10_emit_report_and_alerts", "Emit report and alerts"),
)


@dataclass
class DagStepResult:
    step: str
    name: str
    status: str = "pending"
    started_at: str | None = None
    finished_at: str | None = None
    duration_seconds: float | None = None
    details: dict[str, object] = field(default_factory=dict)
    error: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "step": self.step,
            "name": self.name,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_seconds": self.duration_seconds,
            "details": self.details,
            "error": self.error,
        }


def new_step_results() -> list[DagStepResult]:
    return [
        DagStepResult(
            step=step_id,
            name=step_name,
        )
        for step_id, step_name in DAILY_DAG_STEPS
    ]


def step_result(step_results: list[DagStepResult], step_id: str) -> DagStepResult:
    for result in step_results:
        if result.step == step_id:
            return result
    raise ValueError(f"Unknown DAG step id: {step_id}")


def run_dag_step(
    step_results: list[DagStepResult],
    *,
    step_id: str,
    run_fn: Callable[[], dict[str, object] | None],
    now_iso: Callable[[], str],
) -> DagStepResult:
    result = step_result(step_results, step_id)
    start_time = dt.datetime.now(dt.timezone.utc)
    result.status = "running"
    result.started_at = now_iso()
    try:
        details = run_fn() or {}
    except Exception as exc:
        finish_time = dt.datetime.now(dt.timezone.utc)
        result.status = "failed"
        result.finished_at = now_iso()
        result.duration_seconds = round((finish_time - start_time).total_seconds(), 6)
        result.error = str(exc)
        raise

    finish_time = dt.datetime.now(dt.timezone.utc)
    result.status = "ok"
    result.finished_at = now_iso()
    result.duration_seconds = round((finish_time - start_time).total_seconds(), 6)
    result.details = details
    return result


def skip_dag_step(
    step_results: list[DagStepResult],
    *,
    step_id: str,
    reason: str,
    now_iso: Callable[[], str],
    details: dict[str, object] | None = None,
) -> DagStepResult:
    result = step_result(step_results, step_id)
    now = now_iso()
    result.status = "skipped"
    result.started_at = now
    result.finished_at = now
    result.duration_seconds = 0.0
    payload = dict(details or {})
    payload["reason"] = reason
    result.details = payload
    return result


def serialize_step_results(step_results: list[DagStepResult]) -> list[dict[str, object]]:
    return [step.as_dict() for step in step_results]


def completed_steps_from_dag(step_results: list[DagStepResult]) -> list[dict[str, object]]:
    completed: list[dict[str, object]] = []
    for step in step_results:
        status = step.status
        if status not in TERMINAL_STEP_STATUSES:
            continue
        completed.append(
            {
                "step": step.step,
                "status": status,
                "details": step.details,
            }
        )
    return completed


def failed_step_id(step_results: list[DagStepResult]) -> str | None:
    for step in step_results:
        if step.status == "failed":
            return step.step
    return None
