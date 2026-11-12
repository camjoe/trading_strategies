from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

CI_REGISTRY_REL = "apps/paper_trading_web/frontend/src/assets/ci.json"
WORKFLOW_REL = ".github/workflows/ci.yml"
PATHS_FILTER_ACTION = "dorny/paths-filter"

CHANGE_OUTPUT = re.compile(r"needs\.\w+\.outputs\.(\w+)")
ALWAYS_ON_PUSH = "github.event_name != 'pull_request'"


def _load_workflow(path: Path) -> dict[Any, Any]:
    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(workflow, dict):
        raise ValueError(f"{path} is not a workflow mapping")
    return workflow


def _triggers(workflow: dict[Any, Any]) -> list[dict[str, Any]]:
    # YAML 1.1 reads the bare key `on` as the boolean True.
    on = workflow.get("on", workflow.get(True))
    if isinstance(on, str):
        on = {on: None}
    elif isinstance(on, list):
        on = dict.fromkeys(on)
    triggers = []
    for event, detail in (on or {}).items():
        branches = detail.get("branches", []) if isinstance(detail, dict) else []
        triggers.append({"event": str(event), "branches": list(branches)})
    return triggers


def _steps(job: dict[str, Any]) -> list[dict[str, Any]]:
    steps = []
    for step in job.get("steps", []):
        uses = step.get("uses")
        run = step.get("run")
        steps.append(
            {
                "name": step.get("name") or uses or "step",
                "uses": uses,
                "run": run.strip() if isinstance(run, str) else None,
            }
        )
    return steps


def _path_filters(job: dict[str, Any]) -> dict[str, list[str]]:
    for step in job.get("steps", []):
        if str(step.get("uses", "")).startswith(PATHS_FILTER_ACTION):
            filters = yaml.safe_load(step.get("with", {}).get("filters", "")) or {}
            return {name: list(globs) for name, globs in filters.items()}
    return {}


def _job(job_id: str, job: dict[str, Any]) -> dict[str, Any]:
    needs = job.get("needs", [])
    condition = " ".join(str(job["if"]).split()) if "if" in job else None
    return {
        "id": job_id,
        "name": job.get("name", job_id),
        "needs": [needs] if isinstance(needs, str) else list(needs),
        "runs_on": job.get("runs-on"),
        "condition": condition,
        "always_on_push": bool(condition and ALWAYS_ON_PUSH in condition),
        "when_changed": sorted(set(CHANGE_OUTPUT.findall(condition or ""))),
        "path_filters": _path_filters(job),
        "steps": _steps(job),
    }


def build_payload(repo_root: Path) -> dict[str, Any]:
    workflow = _load_workflow(repo_root / WORKFLOW_REL)
    return {
        "schema_version": 1,
        "file": WORKFLOW_REL,
        "name": workflow.get("name", WORKFLOW_REL),
        "triggers": _triggers(workflow),
        "jobs": [_job(job_id, job) for job_id, job in workflow.get("jobs", {}).items()],
    }
