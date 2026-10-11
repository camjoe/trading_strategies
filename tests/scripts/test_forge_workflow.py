import re

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

    assert {name for name, _ in calls} == {"review-context", "comment-get", "check-body", "comment-upsert"}
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
