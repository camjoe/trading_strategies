import re
import subprocess
from pathlib import Path

from common.git import get_repo_root
from scripts.forge.cli import build_parser
from scripts.forge.service import review_context
from tests.scripts.test_forge import StubForge

WORKFLOW = get_repo_root() / ".github" / "workflows" / "pr-readiness.yml"


def _flags_by_command() -> dict[str, set[str]]:
    subparsers = next(action for action in build_parser()._actions if getattr(action, "choices", None))
    return {
        name: {option for action in parser._actions for option in action.option_strings}
        for name, parser in subparsers.choices.items()
    }


def _forge_calls() -> list[tuple[str, list[str]]]:
    text = WORKFLOW.read_text(encoding="utf-8").replace("\\\n", " ")
    return [
        (match.group(1), re.findall(r"(--[a-z-]+)", match.group(2)))
        for match in re.finditer(r"-m scripts\.forge ([a-z-]+)([^\n]*)", text)
    ]


def test_every_forge_call_in_the_workflow_uses_flags_the_command_accepts() -> None:
    known = _flags_by_command()
    calls = _forge_calls()

    assert {name for name, _ in calls} == {"review-context", "comment-get", "check-body", "pr-info", "comment-upsert"}
    for name, flags in calls:
        assert set(flags) <= known[name], f"{name}: {set(flags) - known[name]}"


def test_the_workflow_reads_keys_that_review_context_returns() -> None:
    context = review_context(StubForge(), 7, [])
    keys = re.findall(r"jq -r '\.([a-z_]+)", WORKFLOW.read_text(encoding="utf-8"))

    assert keys
    assert set(keys) <= set(context)


def test_the_workflow_checks_the_body_before_it_posts() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert text.index("- name: Check the comment body") < text.index("- name: Post the readiness comment")


def test_the_check_step_runs_check_body_and_the_post_step_runs_comment_upsert() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    check_step = text[text.index("- name: Check the comment body") : text.index("- name: Post the readiness comment")]
    post_step = text[text.index("- name: Post the readiness comment") :]

    assert "scripts.forge check-body" in check_step
    assert "scripts.forge comment-upsert" in post_step.split("- name:")[1]


def test_every_shell_variable_the_workflow_reads_is_defined_in_it() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    used = set(re.findall(r"\$\{?([A-Z][A-Z0-9_]+)", text))
    defined = set(re.findall(r"^\s+([A-Z][A-Z0-9_]+):", text, re.MULTILINE))
    defined |= set(re.findall(r'echo "([A-Z][A-Z0-9_]+)=', text))
    defined |= set(re.findall(r'write\(f"([A-Z][A-Z0-9_]+)=', text))
    provided_by_the_runner = {"RUNNER_TEMP", "GITHUB_ENV", "GITHUB_OUTPUT", "GITHUB_STEP_SUMMARY"}

    assert {"HEAD_SHA", "MAX_PASSES", "PR_NUMBER"} <= used
    assert used <= defined | provided_by_the_runner, used - defined - provided_by_the_runner


def _job(name: str) -> str:
    text = WORKFLOW.read_text(encoding="utf-8")
    starts = {job: text.index(f"\n  {job}:\n") for job in ("review", "post")}
    later = [index for index in starts.values() if index > starts[name]]
    return text[starts[name] : min(later)] if later else text[starts[name] :]


def test_the_agent_job_never_posts_and_never_holds_the_github_token_after_the_agent_starts() -> None:
    review = _job("review")
    after_agent = review[review.index("- name: Run pr ready") :]

    assert "comment-upsert" not in review and "check-body" not in review
    assert "GH_TOKEN" not in after_agent and "github.token" not in after_agent


def test_the_posting_job_starts_from_a_fresh_checkout_and_never_runs_the_agent() -> None:
    post = _job("post")

    assert "needs: review" in post and "actions/checkout" in post and "download-artifact" in post
    assert "claude " not in post and "npm install" not in post
    assert post.index("actions/checkout") < post.index("download-artifact") < post.index("comment-upsert")


def test_the_job_that_posts_keeps_the_name_readiness() -> None:
    assert "name: readiness\n" in _job("post") and "name: readiness-review\n" in _job("review")


def test_the_transcript_is_scrubbed_with_the_system_python_not_the_agents_venv() -> None:
    review = _job("review")
    scrub = review[review.index("- name: Scrub the transcript") : review.index("- name: Transcript artifact")]

    assert "python3 -" in scrub and ".venv" not in scrub


def test_the_posting_job_confirms_the_head_has_not_moved_just_before_it_posts() -> None:
    post = _job("post")
    confirm = post.index("- name: Confirm the pull request head has not moved")

    assert post.index("- name: Check the comment body") < confirm < post.index("- name: Post the readiness comment")
    assert "scripts.forge pr-info" in post[confirm : post.index("- name: Post the readiness comment")]


def test_a_failed_review_turns_the_readiness_check_red_instead_of_skipped() -> None:
    post = _job("post")
    first_step = post[post.index("steps:") : post.index("- name: Checkout")]

    assert "!cancelled()" in post.split("steps:")[0]
    assert "needs.review.result != 'success'" in first_step and "exit 1" in first_step


def test_the_two_jobs_agree_on_the_artifact_and_the_body_file() -> None:
    assert "name: readiness-body" in _job("review") and "name: readiness-body" in _job("post")
    assert "readiness-comment.md" in _job("review") and "readiness-comment.md" in _job("post")
    assert "overwrite: true" in _job("review")


def _head_check_script() -> str:
    post = _job("post")
    step = post[post.index("- name: Confirm the pull request head has not moved") :]
    body = step.split("<<'PY'")[1].split("          PY")[0]
    return "".join(line[10:] + chr(10) for line in body.splitlines()[1:])


def _run_head_check(tmp_path: Path, reviewed: str, current: str) -> subprocess.CompletedProcess[str]:
    import json
    import sys

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


def test_each_job_asks_for_only_the_permissions_it_uses() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    header = text[: text.index("\njobs:\n")]
    review, post = _job("review"), _job("post")

    assert "pull-requests: write" not in header and "pull-requests: write" not in review
    assert "pull-requests: write" in post and "checks:" not in post


def _allowed_tools() -> list[str]:
    review = _job("review")
    line = next(line for line in review.splitlines() if "ALLOWED_TOOLS:" in line)
    return line.split("ALLOWED_TOOLS:")[1].strip().split(",")


def test_the_review_agent_may_run_exactly_these_commands() -> None:
    assert sorted(_allowed_tools()) == sorted(
        [
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
    )


def test_no_allowed_entry_lets_the_agent_run_an_arbitrary_python_command() -> None:
    interpreters = ("python", ".venv/bin/python", "./.venv/bin/python")
    for entry in _allowed_tools():
        if entry.startswith("Bash("):
            command = entry[len("Bash(") : -len(")")]
            assert command not in tuple(f"{name}:*" for name in interpreters), entry


def test_the_skill_tells_the_unattended_agent_to_use_ci_as_the_gate_and_the_allowed_scope_check_form() -> None:
    skill = (WORKFLOW.parents[2] / ".ai" / "skills" / "check-pr-readiness" / "SKILL.md").read_text(encoding="utf-8")

    assert "Unattended in CI" in skill and "`ci.state` as the gate result" in skill
    assert ".venv/bin/python -m scripts.checks.repo.review_scope_check --base <base_ref>" in skill


def test_nothing_after_the_agent_starts_uses_the_agents_virtualenv_with_the_claude_token() -> None:
    review = _job("review")
    after = review[review.index("- name: Run pr ready") :]
    steps = after.split("      - name:")

    scripts = [step.split("run: |")[1] for step in steps if "CLAUDE_CODE_OAUTH_TOKEN" in step and "run: |" in step]

    assert scripts and all(".venv/bin/python" not in script for script in scripts)


def _agent_step() -> str:
    review = _job("review")
    start = review.index("- name: Run pr ready")
    return review[start : review.index("- name:", start + 10)]


def test_the_agents_denied_tools_include_monitor_and_are_passed_to_the_claude_call() -> None:
    step = _agent_step()
    env_line = next(line for line in step.splitlines() if line.strip().startswith("DENIED_TOOLS:"))

    assert "Monitor" in env_line.split("DENIED_TOOLS:")[1].strip().split(",")
    assert '--disallowedTools "$DENIED_TOOLS"' in step.split("run: |")[1]


def test_the_prompt_tells_the_agent_to_use_plan_subagents_and_not_to_poll() -> None:
    review = _job("review")
    prompt = review[review.index("- name: Build the prompt") : review.index("- name: Run pr ready")]

    assert "subagent_type Plan" in prompt and "do not poll" in prompt and "sleep loops, Monitor" in prompt
