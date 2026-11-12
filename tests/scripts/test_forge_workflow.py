import json
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

from common.git import get_repo_root
from scripts.forge import tools
from scripts.forge.cli import build_parser
from scripts.forge.service import review_context
from tests.scripts.test_forge import StubForge

ROOT = get_repo_root()
WORKFLOW = ROOT / ".github" / "workflows" / "pr-readiness.yml"
SKILL = ROOT / ".ai" / "skills" / "check-pr-readiness" / "SKILL.md"

PINNED_ALLOWED_TOOLS = [
    "Read",
    "Glob",
    "Grep",
    "Skill",
    "Agent",
    "Write",
    "Bash(git:*)",
    "Bash(.venv/bin/python -m scripts.checks.repo.review_scope_check:*)",
    "Bash(./.venv/bin/python -m scripts.checks.repo.review_scope_check:*)",
    "Bash(cat:*)",
    "Bash(ls:*)",
]
# The arguments of the reviewer's `claude -p` call, between the command and the stdin redirect.
REVIEWER_CALL = re.compile(r"claude -p (.*?) <", re.DOTALL)
REVIEWER_FLAGS = [
    "--output-format", "stream-json", "--verbose",
    "--permission-mode", "dontAsk", "--permission-prompts", "none", "--strict-mcp-config",
    "--allowedTools", "$ALLOWED_TOOLS", "--disallowedTools", "$DENIED_TOOLS",
]  # fmt: skip
PINNED_DENIED_TOOLS = ["Bash(git push:*)", "Bash(gh:*)", "Monitor"]


def _workflow() -> dict[str, Any]:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _steps(job: str) -> list[dict[str, Any]]:
    return _workflow()["jobs"][job]["steps"]


def _names(job: str) -> list[str]:
    return [step["name"] for step in _steps(job)]


def _step(job: str, name: str) -> dict[str, Any]:
    return next(step for step in _steps(job) if step["name"] == name)


def _run(job: str, name: str) -> str:
    return _step(job, name)["run"]


def _job(job: str) -> dict[str, Any]:
    return _workflow()["jobs"][job]


def _directory(job: str, step: dict[str, Any]) -> str | None:
    """Where *step* runs: its own working directory, else the job's default."""
    return step.get("working-directory") or _job(job).get("defaults", {}).get("run", {}).get("working-directory")


def _variable(job: str, step: dict[str, Any], name: str) -> str | None:
    """The value *step* sees for *name*: its own, else the job's."""
    return step.get("env", {}).get(name) or _job(job).get("env", {}).get(name)


# `python -m scripts.forge <command> <rest of that line>` as written in the workflow.
FORGE_CALL = re.compile(r"-m scripts\.forge ([a-z-]+)([^\n]*)")
LONG_FLAG = re.compile(r"(--[a-z-]+)")
# `jq -r '.key'`: a key the workflow reads from the review-context JSON.
JQ_KEY = re.compile(r"jq -r '\.([a-z_]+)")
# `$NAME` or `${NAME}`: a shell variable the workflow reads.
SHELL_VARIABLE_READ = re.compile(r"\$\{?([A-Z][A-Z0-9_]+)")
# The three ways the workflow defines a variable: a YAML `env:` key, `echo "NAME=..."`, `write(f"NAME=...")`.
YAML_ENV_KEY = re.compile(r"^\s+([A-Z][A-Z0-9_]+):", re.MULTILINE)
ECHO_ASSIGNMENT = re.compile(r'echo "([A-Z][A-Z0-9_]+)=')
PYTHON_ASSIGNMENT = re.compile(r'write\(f"([A-Z][A-Z0-9_]+)=')


def _flags_by_command() -> dict[str, set[str]]:
    subparsers = next(action for action in build_parser()._actions if getattr(action, "choices", None))
    return {
        name: {option for action in parser._actions for option in action.option_strings}
        for name, parser in subparsers.choices.items()
    }


def _forge_calls() -> list[tuple[str, list[str]]]:
    text = WORKFLOW.read_text(encoding="utf-8").replace("\\\n", " ")
    return [(match.group(1), LONG_FLAG.findall(match.group(2))) for match in FORGE_CALL.finditer(text)]


def test_every_forge_call_in_the_workflow_uses_flags_the_command_accepts() -> None:
    known = _flags_by_command()
    calls = _forge_calls()

    assert {name for name, _ in calls} == {
        "review-context",
        "comment-get",
        "check-body",
        "pr-info",
        "comment-upsert",
        "inline-sync",
    }
    for name, flags in calls:
        assert set(flags) <= known[name], f"{name}: {set(flags) - known[name]}"


def test_the_workflow_reads_keys_that_review_context_returns() -> None:
    context = review_context(StubForge(), 7, [])
    keys = JQ_KEY.findall(WORKFLOW.read_text(encoding="utf-8"))

    assert keys
    assert set(keys) <= set(context)


def test_every_shell_variable_the_workflow_reads_is_defined_in_it() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    used = set(SHELL_VARIABLE_READ.findall(text))
    defined = (
        set(YAML_ENV_KEY.findall(text)) | set(ECHO_ASSIGNMENT.findall(text)) | set(PYTHON_ASSIGNMENT.findall(text))
    )
    provided_by_the_runner = {"RUNNER_TEMP", "GITHUB_ENV", "GITHUB_OUTPUT", "GITHUB_STEP_SUMMARY"}

    assert {"HEAD_SHA", "MAX_PASSES", "PR_NUMBER"} <= used
    assert used <= defined | provided_by_the_runner, used - defined - provided_by_the_runner


def test_the_posting_job_checks_confirms_and_posts_in_that_order() -> None:
    names = _names("post")
    check = names.index("Check the comment body")
    confirm = names.index("Confirm the pull request head has not moved")
    post = names.index("Post the readiness comment")

    assert check < confirm < post
    assert "scripts.forge check-body" in _run("post", "Check the comment body")
    assert "scripts.forge pr-info" in _run("post", "Confirm the pull request head has not moved")
    assert "scripts.forge comment-upsert" in _run("post", "Post the readiness comment")


def test_the_agent_job_never_posts_and_holds_no_github_token_once_the_agent_starts() -> None:
    steps = _steps("review")
    started = _names("review").index("Run pr ready")

    for step in steps:
        assert "comment-upsert" not in step.get("run", "") and "check-body" not in step.get("run", "")
    for step in steps[started:]:
        assert "GH_TOKEN" not in step.get("env", {}) and "github.token" not in json.dumps(step)


def test_the_posting_job_starts_from_a_fresh_checkout_and_never_runs_the_agent() -> None:
    job = _workflow()["jobs"]["post"]
    names = _names("post")
    uses = [step.get("uses", "") for step in job["steps"]]
    post_text = json.dumps(job)

    assert job["needs"] == "review"
    assert "claude " not in post_text and "npm install" not in post_text
    checkout_at = next(index for index, value in enumerate(uses) if value.startswith("actions/checkout@"))
    download_at = next(index for index, value in enumerate(uses) if value.startswith("actions/download-artifact@"))
    assert checkout_at < download_at < names.index("Post the readiness comment")


def test_the_job_that_posts_keeps_the_name_readiness() -> None:
    jobs = _workflow()["jobs"]

    assert jobs["post"]["name"] == "readiness" and jobs["review"]["name"] == "readiness-review"


def test_the_transcript_is_scrubbed_with_the_system_python_not_the_agents_venv() -> None:
    script = _run("review", "Scrub the transcript")

    assert "python3 -" in script and ".venv" not in script


def _head_check_script() -> str:
    run = _run("post", "Confirm the pull request head has not moved")
    return run.split("<<'PY'\n")[1].split("\nPY")[0]


def _run_head_check(tmp_path: Path, reviewed: str, current: str) -> subprocess.CompletedProcess[str]:
    (tmp_path / "pr.json").write_text(json.dumps({"head_sha": current}), encoding="utf-8")
    return subprocess.run(
        [sys.executable, "-c", _head_check_script()],
        env={"RUNNER_TEMP": str(tmp_path), "HEAD_SHA": reviewed},
        capture_output=True,
        text=True,
    )


def test_the_head_check_passes_when_the_head_is_the_reviewed_commit(tmp_path: Path) -> None:
    assert _run_head_check(tmp_path, "abc", "abc").returncode == 0


def test_the_head_check_fails_with_an_error_when_the_head_moved(tmp_path: Path) -> None:
    result = _run_head_check(tmp_path, "abc", "def")

    assert result.returncode != 0 and "moved to def" in result.stderr


def test_a_failed_review_turns_the_readiness_check_red_instead_of_skipped() -> None:
    job = _workflow()["jobs"]["post"]
    first = job["steps"][0]

    assert job["if"].startswith("!cancelled()")
    assert first["if"] == "needs.review.result != 'success'" and "exit 1" in first["run"]


def test_the_two_jobs_agree_on_the_artifact_and_the_body_file() -> None:
    upload = _step("review", "Hand over the comment body")
    download = _step("post", "Fetch the handed-over comment body")
    reads_body = _run("post", "Read the pass number of the comment being replaced")

    assert upload["with"]["name"] == download["with"]["name"] == "readiness-body"
    assert upload["with"]["overwrite"] is True and upload["with"]["if-no-files-found"] == "error"
    assert upload["with"]["path"].endswith("/readiness-comment.md")
    assert "handoff/readiness-comment.md" in reads_body
    assert download["with"]["path"].endswith("/handoff")


def test_each_job_asks_for_only_the_permissions_it_uses() -> None:
    workflow = _workflow()

    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["jobs"]["review"]["permissions"] == {
        "contents": "read",
        "checks": "read",
        "pull-requests": "read",
    }
    assert workflow["jobs"]["post"]["permissions"] == {"contents": "read", "pull-requests": "write"}


def test_the_review_agent_may_run_exactly_these_tools_and_the_claude_call_uses_them() -> None:
    step = _step("review", "Run pr ready")
    allowed = step["env"]["ALLOWED_TOOLS"].split(",")
    denied = step["env"]["DENIED_TOOLS"].split(",")
    run = step["run"]

    assert sorted(allowed) == sorted(PINNED_ALLOWED_TOOLS)
    assert sorted(denied) == sorted(PINNED_DENIED_TOOLS)
    assert '< "$PROMPT_FILE"' in run
    assert "--dangerously" not in run
    call = REVIEWER_CALL.search(run.replace("\\\n", " "))
    assert call and shlex.split(call.group(1)) == REVIEWER_FLAGS


def test_the_reviewer_passes_the_same_deny_by_default_options_as_the_agent_runners() -> None:
    options = list(tools.DENY_BY_DEFAULT_OPTIONS)
    start = REVIEWER_FLAGS.index(options[0])

    assert REVIEWER_FLAGS[start : start + len(options)] == options


def test_no_allowed_entry_lets_the_agent_run_an_arbitrary_python_command() -> None:
    bare = {f"{name}:*" for name in ("python", "python3", ".venv/bin/python", "./.venv/bin/python")}
    for entry in _step("review", "Run pr ready")["env"]["ALLOWED_TOOLS"].split(","):
        if entry.startswith("Bash("):
            assert entry[len("Bash(") : -len(")")] not in bare, entry


def test_nothing_after_the_agent_starts_uses_the_agents_virtualenv_with_the_claude_token() -> None:
    steps = _steps("review")[_names("review").index("Run pr ready") :]
    holding = [step for step in steps if "CLAUDE_CODE_OAUTH_TOKEN" in step.get("env", {}) and "run" in step]

    assert holding and all(".venv/bin/python" not in step["run"] for step in holding)


def test_the_prompt_tells_the_agent_to_use_plan_subagents_and_not_to_poll() -> None:
    script = _run("review", "Build the prompt")

    assert "subagent_type Plan" in script and "do not poll" in script and "sleep loops, Monitor" in script
    assert "Do NOT run the gate" in script and "review_scope_check" in script


def test_the_skill_tells_the_unattended_agent_to_use_ci_as_the_gate_and_the_allowed_scope_check_form() -> None:
    skill = SKILL.read_text(encoding="utf-8")

    assert "Unattended in CI" in skill and "`ci.state` as the gate result" in skill
    assert "`pass`" in skill and "continues to Step 2" in skill
    assert ".venv/bin/python -m scripts.checks.repo.review_scope_check --base <base_ref>" in skill


def test_the_skill_says_security_findings_do_not_decide_the_title_and_points_to_the_owners_decision() -> None:
    skill = SKILL.read_text(encoding="utf-8")

    assert "do not decide the title" in skill and "run /security-review before merge" in skill
    assert "The title follows the rules above only." in skill


def _uses(job: str, prefix: str) -> list[dict[str, Any]]:
    return [step for step in _steps(job) if step.get("uses", "").startswith(prefix)]


def test_both_jobs_take_the_forge_tool_from_the_base_branch_into_a_separate_directory() -> None:
    for job in ("review", "post"):
        trusted = [step for step in _uses(job, "actions/checkout@") if step["with"].get("path") == "trusted"]

        assert len(trusted) == 1, job
        assert trusted[0]["with"]["ref"] == "${{ github.base_ref }}"
        assert trusted[0]["with"]["persist-credentials"] is False


def test_the_posting_job_never_checks_out_the_pull_request() -> None:
    checkouts = _uses("post", "actions/checkout@")

    assert len(checkouts) == 1
    assert checkouts[0]["with"]["ref"] == "${{ github.base_ref }}" and checkouts[0]["with"]["path"] == "trusted"
    assert ".venv" not in json.dumps(_steps("post"))


def test_the_pull_request_is_checked_out_before_the_trusted_copy_so_the_clean_cannot_delete_it() -> None:
    names = _names("review")

    assert names.index("Checkout the PR head") < names.index("Checkout the forge tool from the base branch")


def test_every_forge_call_runs_from_the_trusted_copy_with_its_source_on_the_path() -> None:
    forge_steps = [
        (job, step)
        for job in ("review", "post")
        for step in _steps(job)
        if "scripts.forge" in step.get("run", "") or "scripts.forge" in json.dumps(step)
    ]

    assert len(forge_steps) >= 5
    for job, step in forge_steps:
        assert _directory(job, step) == "trusted", (job, step["name"])
        assert _variable(job, step, "PYTHONPATH") == "src", (job, step["name"])
        assert ".venv" not in step["run"], (job, step["name"])


def test_the_post_job_runs_from_the_trusted_copy_unless_the_copy_does_not_exist_yet() -> None:
    post = _job("post")
    explicit = [step["name"] for step in post["steps"] if "working-directory" in step]
    checkout = next(i for i, step in enumerate(post["steps"]) if step.get("with", {}).get("path") == "trusted")
    before_checkout = [step["name"] for step in post["steps"][:checkout] if "run" in step]

    assert post["defaults"]["run"]["working-directory"] == "trusted" and post["env"]["PYTHONPATH"] == "src"
    assert explicit == before_checkout == ["Fail when the review job did not succeed"]
    assert _step("post", explicit[0])["working-directory"] == "${{ github.workspace }}"


def test_the_prompt_is_built_with_the_system_python_not_the_pull_requests_virtualenv() -> None:
    run = _run("review", "Build the prompt")

    assert run.startswith("python3 - <<") and ".venv/bin/python - <<" not in run


def test_the_claude_token_is_in_the_posting_job_only_for_the_body_check() -> None:
    holding = [step["name"] for step in _steps("post") if "CLAUDE_CODE_OAUTH_TOKEN" in json.dumps(step)]

    assert holding == ["Check the comment body"]


def test_the_prompt_tells_the_agent_to_use_a_placeholder_for_user_names_in_example_paths() -> None:
    script = _run("review", "Build the prompt")

    assert "write `<user>` in place of any user" in script and "do not copy sample paths out of tests" in script
