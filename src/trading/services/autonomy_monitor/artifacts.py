"""Artifact reading for autonomy monitoring.

This module reads exported JSON artifacts from the trading runtime jobs:
- Daily paper trading runs (daily_paper_trading_*.json)
- Governance checks (weekly_governance_*/*, monthly_governance_*/*)
- Burn-in status (check_burn_in_status_*.json)

All artifact paths are relative to local/ folder.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from common.files import sorted_by_mtime_desc
from common.paths.repo_paths import get_repo_root


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


def _governance_result(pattern: str, export_dir: Path) -> dict[str, Any]:
    artifact = _find_latest_artifact(pattern, export_dir)
    if not artifact:
        return {
            "status": "not_run",
            "last_run": None,
            "has_results": False,
            "result": None,
        }
    return {
        "status": "success" if artifact.get("success", True) else "failed",
        "last_run": artifact.get("run_timestamp") or artifact.get("generated_at"),
        "has_results": True,
        "result": artifact,
    }


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

    return {
        "status": "success" if artifact.get("success") else "failed",
        "latest_run_time": artifact.get("run_timestamp"),
        "step_results": artifact.get("steps", []),
        "completed_steps": len([s for s in artifact.get("steps", []) if s.get("status") == "completed"]),
        "duration_seconds": artifact.get("duration_seconds"),
        "failed_step": artifact.get("failed_step"),
    }


def fetch_governance_checks_status(repo_root: Path | None = None) -> dict[str, Any]:
    """Fetch governance check statuses (weekly W1-W3, monthly M1-M3).

    Returns dict mapping check names to status and last run timestamp.
    """
    if repo_root is None:
        repo_root = get_repo_root(__file__)

    export_dir = repo_root / "local" / "exports"

    return {
        "w1_leaderboard": _governance_result("weekly_governance_*/w1_leaderboard_*.json", export_dir),
        "w2_promotion": _governance_result("weekly_governance_*/w2_promotion_*.json", export_dir),
        "w3_allocation": _governance_result("weekly_governance_*/w3_allocation_*.json", export_dir),
        "m1_risk_rebaseline": _governance_result("monthly_governance_*/m1_risk_*.json", export_dir),
        "m2_parameter_governance": _governance_result("monthly_governance_*/m2_parameter_*.json", export_dir),
        "m3_performance_audit": _governance_result("monthly_governance_*/m3_performance_*.json", export_dir),
    }


def fetch_burn_in_status(repo_root: Path | None = None) -> dict[str, Any]:
    """Fetch burn-in progress from latest artifact.

    Returns dict with consecutive successes, min required, ready status, and check time.
    """
    if repo_root is None:
        repo_root = get_repo_root(__file__)

    artifact_dir = repo_root / "local" / "artifacts"
    artifact = _find_latest_artifact("check_burn_in_status_*.json", artifact_dir)

    if not artifact:
        return {
            "consecutive_successes": 0,
            "min_required_successes": 10,
            "ready_for_live": False,
            "last_checked": None,
        }

    return {
        "consecutive_successes": artifact.get("consecutive_successes", 0),
        "min_required_successes": artifact.get("min_required_successes", 10),
        "ready_for_live": artifact.get("ready_for_live", False),
        "last_checked": artifact.get("check_time"),
    }
