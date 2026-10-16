import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts.ci import changed_scope

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
# `"<group>=$<VARIABLE>"`, the way the workflow passes each path list to the helper.
GROUP_ARGUMENT = re.compile(r'"(\w+)=\$(\w+)"')
# `needs.changes.outputs.<group>`, the way the other jobs read the result.
OUTPUT_USE = re.compile(r"needs\.changes\.outputs\.(\w+)")


def _git(directory: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=directory, check=True, capture_output=True, text=True)


def _commit(directory: Path, files: dict[str, str], message: str) -> None:
    for name, content in files.items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    _git(directory, "add", "-A")
    _git(directory, "commit", "-q", "-m", message)


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A repository on `feature`, branched from `main`, with a source directory, a docs directory and one loose file."""
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.name", "Test")
    _git(tmp_path, "config", "user.email", "test@example.test")
    _commit(tmp_path, {"src/a.py": "1", "docs/x.md": "1", "pytest.ini": "1"}, "base")
    _git(tmp_path, "switch", "-q", "-c", "feature")
    monkeypatch.chdir(tmp_path)
    return tmp_path


class TestChanged:
    def test_a_change_under_a_listed_directory_is_seen(self, repo: Path) -> None:
        _commit(repo, {"src/a.py": "2"}, "edit")

        assert changed_scope.changed("main", ["src"]) is True
        assert changed_scope.changed("main", ["docs"]) is False

    def test_a_change_to_a_listed_file_is_seen(self, repo: Path) -> None:
        _commit(repo, {"pytest.ini": "2"}, "edit")

        assert changed_scope.changed("main", ["pytest.ini"]) is True
        assert changed_scope.changed("main", ["src", "docs"]) is False

    def test_a_new_file_under_a_listed_directory_is_seen(self, repo: Path) -> None:
        _commit(repo, {"docs/new/y.md": "1"}, "add")

        assert changed_scope.changed("main", ["docs"]) is True

    def test_nothing_changed_means_false(self, repo: Path) -> None:
        assert changed_scope.changed("main", ["src", "docs", "pytest.ini"]) is False

    def test_changes_made_on_the_base_after_branching_do_not_count(self, repo: Path) -> None:
        _git(repo, "switch", "-q", "main")
        _commit(repo, {"docs/y.md": "1"}, "later on main")
        _git(repo, "switch", "-q", "feature")

        assert changed_scope.changed("main", ["docs"]) is False

    def test_a_git_error_counts_as_a_change_so_no_check_is_skipped(self, repo: Path) -> None:
        assert changed_scope.changed("no-such-branch", ["src"]) is True


class TestCommandLine:
    def test_it_prints_one_line_per_group(self, repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        _commit(repo, {"src/a.py": "2"}, "edit")

        code = changed_scope.main(["main", "python_related=src tests", "docs_related=docs"])

        assert code == 0
        assert capsys.readouterr().out.splitlines() == ["python_related=true", "docs_related=false"]

    @pytest.mark.parametrize("argv", [[], ["main"], ["main", "no-equals-sign"], ["main", "empty="], ["main", "=src"]])
    def test_a_missing_base_or_a_malformed_group_is_a_usage_error(
        self, argv: list[str], capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert changed_scope.main(argv) == 2
        assert capsys.readouterr().out == ""


def _changes_job(workflow: dict[str, Any]) -> dict[str, Any]:
    return workflow["jobs"]["changes"]


def _scope_step(workflow: dict[str, Any]) -> dict[str, Any]:
    return next(step for step in _changes_job(workflow)["steps"] if step.get("id") == "scope")


@pytest.mark.parametrize("name", ["ci", "security-checks"])
class TestWorkflowWiring:
    def _workflow(self, name: str) -> dict[str, Any]:
        return yaml.safe_load((WORKFLOWS / f"{name}.yml").read_text(encoding="utf-8"))

    def test_the_step_runs_only_on_pull_requests_from_a_full_checkout(self, name: str) -> None:
        job = _changes_job(self._workflow(name))
        checkout = next(step for step in job["steps"] if str(step.get("uses", "")).startswith("actions/checkout@"))

        assert _scope_step(self._workflow(name))["if"] == "github.event_name == 'pull_request'"
        assert checkout["with"]["fetch-depth"] == 0

    def test_every_listed_path_names_something_the_repository_tracks(self, name: str) -> None:
        env = _scope_step(self._workflow(name))["env"]
        paths = [path for variable, value in env.items() if variable != "BASE_REF" for path in value.split()]

        assert paths
        for path in paths:
            listed = subprocess.run(["git", "ls-files", "--", path], cwd=ROOT, capture_output=True, text=True)
            assert listed.stdout.strip(), f"{name}: {path} matches no tracked file"

    def test_each_group_is_passed_to_the_helper_and_exposed_as_a_job_output(self, name: str) -> None:
        workflow = self._workflow(name)
        step = _scope_step(workflow)
        groups = GROUP_ARGUMENT.findall(step["run"])

        assert groups
        assert all(variable in step["env"] for _, variable in groups)
        assert {group: f"${{{{ steps.scope.outputs.{group} }}}}" for group, _ in groups} == _changes_job(workflow)[
            "outputs"
        ]

    def test_the_other_jobs_read_only_groups_the_helper_prints(self, name: str) -> None:
        workflow = self._workflow(name)
        groups = {group for group, _ in GROUP_ARGUMENT.findall(_scope_step(workflow)["run"])}
        used = {
            use
            for job_name, job in workflow["jobs"].items()
            if job_name != "changes"
            for use in OUTPUT_USE.findall(str(job.get("if", "")))
        }

        assert used and used <= groups
