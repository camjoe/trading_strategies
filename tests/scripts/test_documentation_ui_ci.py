from __future__ import annotations

from pathlib import Path

from common.git import get_repo_root
from scripts.documentation_ui.ci.build_registry import run_build
from scripts.documentation_ui.ci.check import run_ci_check
from scripts.documentation_ui.ci.registry import CI_REGISTRY_REL, WORKFLOW_REL, build_payload

WORKFLOW = """
name: Demo
on:
  push:
    branches: [main]
  pull_request:
jobs:
  changes:
    runs-on: ubuntu-latest
    outputs:
      code: ${{ steps.filter.outputs.code }}
    steps:
      - uses: actions/checkout@v6
      - id: filter
        uses: dorny/paths-filter@v3
        with:
          filters: |
            code:
              - src/**
  test:
    needs: changes
    if: github.event_name != 'pull_request' || needs.changes.outputs.code == 'true'
    runs-on: ubuntu-latest
    steps:
      - name: Run tests
        run: |
          python -m pytest
"""


def _write_workflow(root: Path) -> None:
    path = root / WORKFLOW_REL
    path.parent.mkdir(parents=True)
    path.write_text(WORKFLOW, encoding="utf-8")


def test_payload_reads_triggers_jobs_conditions_and_filters(tmp_path: Path) -> None:
    _write_workflow(tmp_path)

    payload = build_payload(tmp_path)
    jobs = {job["id"]: job for job in payload["jobs"]}

    assert payload["name"] == "Demo"
    assert payload["triggers"] == [{"event": "push", "branches": ["main"]}, {"event": "pull_request", "branches": []}]
    assert jobs["changes"]["path_filters"] == {"code": ["src/**"]}
    assert jobs["test"]["needs"] == ["changes"]
    assert jobs["test"]["always_on_push"] is True
    assert jobs["test"]["when_changed"] == ["code"]
    assert jobs["test"]["steps"] == [{"name": "Run tests", "uses": None, "run": "python -m pytest"}]


def test_the_repository_workflow_gates_every_job_on_the_changes_job() -> None:
    jobs = {job["id"]: job for job in build_payload(get_repo_root(__file__))["jobs"]}

    assert jobs["changes"]["needs"] == []
    assert set(jobs["changes"]["path_filters"]) >= {"python_related", "frontend_related"}
    for job_id in ("python", "frontend", "static-checks"):
        assert jobs[job_id]["needs"] == ["changes"]
        assert jobs[job_id]["when_changed"]


def test_check_passes_after_build_and_fails_on_drift(tmp_path: Path) -> None:
    _write_workflow(tmp_path)
    (tmp_path / CI_REGISTRY_REL).parent.mkdir(parents=True)

    run_build(tmp_path)
    assert run_ci_check(tmp_path) == 0

    workflow = tmp_path / WORKFLOW_REL
    workflow.write_text(
        workflow.read_text(encoding="utf-8").replace("python -m pytest", "pytest -x"), encoding="utf-8"
    )
    assert run_ci_check(tmp_path) == 1


def test_check_reports_a_missing_registry(tmp_path: Path) -> None:
    _write_workflow(tmp_path)

    assert run_ci_check(tmp_path) == 2
