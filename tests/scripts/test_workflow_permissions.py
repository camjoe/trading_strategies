import re
from pathlib import Path
from typing import Any

import pytest
import yaml

WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"

# `dorny/paths-filter` reads the pull request's files through the API, so the job that runs it needs this one extra
# permission.
PATHS_FILTER_JOB = "changes"
READ_ONLY = {"contents": "read"}
# `owner/action@<40 hex digits>`: a tag can be moved by its owner, a commit cannot.
FULL_COMMIT = re.compile(r"@[0-9a-f]{40}$")


def _workflow(name: str) -> dict[str, Any]:
    return yaml.safe_load((WORKFLOWS / f"{name}.yml").read_text(encoding="utf-8"))


def test_every_action_not_owned_by_github_is_pinned_to_a_commit() -> None:
    unpinned = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
        for job in workflow["jobs"].values():
            for step in job["steps"]:
                used = str(step.get("uses", ""))
                if used and not used.startswith(("actions/", "./")) and not FULL_COMMIT.search(used):
                    unpinned.append(f"{path.name}: {used}")

    assert unpinned == []


@pytest.mark.parametrize("name", ["ci", "security-checks"])
class TestReadOnlyWorkflows:
    def test_the_token_is_read_only_unless_a_job_asks_for_more(self, name: str) -> None:
        workflow = _workflow(name)

        assert workflow["permissions"] == READ_ONLY
        for job_name, job in workflow["jobs"].items():
            if job_name == PATHS_FILTER_JOB:
                assert job["permissions"] == {**READ_ONLY, "pull-requests": "read"}
            else:
                assert "permissions" not in job, job_name

    def test_every_checkout_drops_the_token_after_cloning(self, name: str) -> None:
        checkouts = [
            step
            for job in _workflow(name)["jobs"].values()
            for step in job["steps"]
            if str(step.get("uses", "")).startswith("actions/checkout@")
        ]

        assert checkouts
        assert all(step.get("with", {}).get("persist-credentials") is False for step in checkouts)

    def test_the_paths_filter_runs_only_in_the_job_that_has_its_permission(self, name: str) -> None:
        for job_name, job in _workflow(name)["jobs"].items():
            uses = [str(step.get("uses", "")) for step in job["steps"]]
            if any(item.startswith("dorny/paths-filter@") for item in uses):
                assert job_name == PATHS_FILTER_JOB
