import re
from pathlib import Path
from typing import Any

import pytest
import yaml

WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"

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
    def test_the_token_is_read_only_in_every_job(self, name: str) -> None:
        workflow = _workflow(name)

        assert workflow["permissions"] == READ_ONLY
        assert all("permissions" not in job for job in workflow["jobs"].values())

    def test_every_checkout_drops_the_token_after_cloning(self, name: str) -> None:
        checkouts = [
            step
            for job in _workflow(name)["jobs"].values()
            for step in job["steps"]
            if str(step.get("uses", "")).startswith("actions/checkout@")
        ]

        assert checkouts
        assert all(step.get("with", {}).get("persist-credentials") is False for step in checkouts)
