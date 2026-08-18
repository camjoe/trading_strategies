"""Artifact reading for autonomy monitoring.

Reads the JSON artifacts the runtime jobs actually write:

- Daily paper trading — ``local/exports/daily_paper_trading/daily_paper_trading_*.json``,
  written by the daily workflow (``status``, ``step_results``, ``completed_steps``,
  ``started_at``/``finished_at``, ``failed_step``).
- Governance W1-W3 / M1-M3 — ``local/artifacts/{job_name}_{period_tag}_*.json``,
  written by the shared job runner. The payload is whatever the job body
  returned; every governance body includes ``generated_at``.
- Burn-in status — ``local/artifacts/check_burn_in_status_*.json``
  (``consecutive_successes``, ``min_consecutive_days``, ``ready_for_live``,
  ``generated_at``).

Keep the key names here in step with those producers — a mismatch reports a
healthy job as missing, which is worse than showing nothing.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

from common.files import sorted_by_mtime_desc
from common.git import get_repo_root
from common.runtime_job_status import TERMINAL_STEP_STATUSES

# Governance job names, in the order an operator reviews them, mapped to the
# response key the UI reads. Artifacts are `{job_name}_{period_tag}_{stamp}.json`.
_GOVERNANCE_JOBS: tuple[tuple[str, str], ...] = (
    ("w1_leaderboard", "weekly_governance_w1_leaderboard"),
    ("w2_promotion", "weekly_governance_w2_promotion_review"),
    ("w3_allocation", "weekly_governance_w3_allocation_review"),
    ("m1_risk_rebaseline", "monthly_governance_m1_risk_rebaseline"),
    ("m2_parameter_governance", "monthly_governance_m2_parameter_governance"),
    ("m3_performance_audit", "monthly_governance_m3_performance_audit"),
)

# Mirrors burn_in_status.py's --min-consecutive-days default, used only when no
# artifact exists yet so the UI can render a target instead of a blank.
_DEFAULT_MIN_CONSECUTIVE_DAYS = 10


def _find_latest_artifact(pattern: str, search_dir: Path) -> dict[str, Any] | None:
    """Find and parse the latest JSON artifact matching a glob pattern."""
    if not search_dir.exists():
        return None

    matching_files = sorted_by_mtime_desc(search_dir.glob(pattern))
    if not matching_files:
        return None

    try:
        with open(matching_files[0], "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError, OSError:
        return None


def _artifacts_dir(repo_root: Path | None) -> Path:
    return (repo_root or get_repo_root(__file__)) / "local" / "artifacts"


def _run_duration_seconds(artifact: dict[str, Any]) -> float | None:
    """Wall-clock seconds between the run's ``started_at`` and ``finished_at``.

    The per-step ``duration_seconds`` values exclude the gaps between steps, so
    the run's own timestamps are the honest total.
    """
    started, finished = artifact.get("started_at"), artifact.get("finished_at")
    if not isinstance(started, str) or not isinstance(finished, str):
        return None
    try:
        return (dt.datetime.fromisoformat(finished) - dt.datetime.fromisoformat(started)).total_seconds()
    except ValueError:
        return None


def fetch_daily_workflow_status(repo_root: Path | None = None) -> dict[str, Any]:
    """Fetch latest daily paper trading run artifact.

    Returns dict with status, steps, duration, and failures.
    """
    if repo_root is None:
        repo_root = get_repo_root(__file__)

    export_dir = repo_root / "local" / "exports"
    artifact = _find_latest_artifact("daily_paper_trading/daily_paper_trading_*.json", export_dir)

    if not artifact:
        return {
            "status": "unknown",
            "latest_run_time": None,
            "step_results": [],
            "completed_steps": 0,
            "duration_seconds": None,
            "failed_step": None,
        }

    step_results = artifact.get("step_results", [])
    if not isinstance(step_results, list):
        step_results = []

    return {
        "status": artifact.get("status", "unknown"),
        "latest_run_time": artifact.get("finished_at") or artifact.get("started_at"),
        "step_results": step_results,
        "completed_steps": sum(
            1 for step in step_results if isinstance(step, dict) and step.get("status") in TERMINAL_STEP_STATUSES
        ),
        "duration_seconds": _run_duration_seconds(artifact),
        "failed_step": artifact.get("failed_step"),
    }


def _governance_result(job_name: str, artifacts_dir: Path) -> dict[str, Any]:
    artifact = _find_latest_artifact(f"{job_name}_*.json", artifacts_dir)
    if not artifact:
        return {
            "status": "not_run",
            "last_run": None,
            "has_results": False,
            "result": None,
        }
    # The runner only writes an artifact once the body returned without raising,
    # so the artifact's existence is the success signal.
    return {
        "status": "success",
        "last_run": artifact.get("generated_at"),
        "has_results": True,
        "result": artifact,
    }


def fetch_governance_checks_status(repo_root: Path | None = None) -> dict[str, Any]:
    """Fetch governance check statuses (weekly W1-W3, monthly M1-M3).

    Returns dict mapping check names to status and last run timestamp.
    """
    artifacts_dir = _artifacts_dir(repo_root)
    return {key: _governance_result(job_name, artifacts_dir) for key, job_name in _GOVERNANCE_JOBS}


def fetch_burn_in_status(repo_root: Path | None = None) -> dict[str, Any]:
    """Fetch burn-in progress from latest artifact.

    Returns dict with consecutive successes, min required, ready status, and check time.
    """
    artifact = _find_latest_artifact("check_burn_in_status_*.json", _artifacts_dir(repo_root))

    if not artifact:
        return {
            "consecutive_successes": 0,
            "min_required_successes": _DEFAULT_MIN_CONSECUTIVE_DAYS,
            "ready_for_live": False,
            "last_checked": None,
        }

    return {
        "consecutive_successes": artifact.get("consecutive_successes", 0),
        "min_required_successes": artifact.get("min_consecutive_days", _DEFAULT_MIN_CONSECUTIVE_DAYS),
        "ready_for_live": artifact.get("ready_for_live", False),
        "last_checked": artifact.get("generated_at"),
    }


__all__ = [
    "fetch_burn_in_status",
    "fetch_daily_workflow_status",
    "fetch_governance_checks_status",
]
