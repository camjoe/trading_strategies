"""Command line for the forge interface: ``python -m scripts.forge <operation>``.

Every operation prints JSON. A failed operation prints ``forge: <reason>`` on stderr and exits 1.
The only comment this tool writes is the readiness comment (``<!-- pr-readiness -->``).
"""

import argparse
import functools
import json
import os
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import asdict
from pathlib import Path

from common.git import get_repo_root, git_output
from scripts.forge.base import Forge, ForgeError
from scripts.forge.fix_loop import result_as_json, run_fix_loop
from scripts.forge.github import GitHubForge
from scripts.forge.implement import run_implement_plan
from scripts.forge.local import LocalGit, email_notifier, run_claude_agent, run_gate
from scripts.forge.readiness import body_problems, fixer_edit_problems, pass_number
from scripts.forge.service import resolve_authors, review_context, wait_for_ci


def _add_pr_argument(command: argparse.ArgumentParser) -> None:
    command.add_argument("--pr", type=int, help="Pull request number (default: the current branch's).")


def _add_author_argument(command: argparse.ArgumentParser) -> None:
    command.add_argument(
        "--author",
        action="append",
        default=[],
        help="Trusted comment author; repeatable (default: the authenticated user).",
    )


def _add_ci_arguments(command: argparse.ArgumentParser) -> None:
    command.add_argument("--exclude", action="append", default=[], help="Check name to ignore; repeatable.")
    command.add_argument("--wait", type=float, default=0, help="Seconds to wait for CI to settle (default: 0).")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m scripts.forge", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    _add_pr_argument(commands.add_parser("pr-info", help="Pull request number, refs, head sha, draft flag, state."))

    comment_get = commands.add_parser("comment-get", help="The readiness comment, or null.")
    _add_pr_argument(comment_get)
    _add_author_argument(comment_get)

    upsert = commands.add_parser("comment-upsert", help="Create or edit the readiness comment from a file.")
    _add_pr_argument(upsert)
    _add_author_argument(upsert)
    upsert.add_argument("--body-file", required=True, help="File holding the comment body, or - for stdin.")

    context = commands.add_parser("review-context", help="Pull request, previous readiness comment, and CI state.")
    _add_pr_argument(context)
    _add_author_argument(context)
    _add_ci_arguments(context)
    context.add_argument("--expect-sha", help="Fail if the pull request head is not this commit.")
    context.add_argument("--max-passes", type=int, help="Report pass_cap_reached once this many passes have run.")

    loop = commands.add_parser(
        "fix-loop", help="Run fixer rounds on a pull request until READY or the owner is needed."
    )
    loop.add_argument("--pr", type=int, required=True, help="Pull request number.")
    _add_author_argument(loop)
    loop.add_argument("--max-rounds", type=int, default=3, help="Fixer rounds before stopping (default: 3).")
    loop.add_argument("--model", default="sonnet", help="Model for the fixer agent (default: sonnet).")
    loop.add_argument(
        "--wait-minutes", type=float, default=45, help="Minutes to wait for each review pass (default: 45)."
    )

    plan = commands.add_parser(
        "implement-plan", help="Claim a plan from plan/, implement it, and open a pull request."
    )
    plan.add_argument("--plan", required=True, help="The plan file, for example plan/foo.md or foo.md.")
    plan.add_argument("--base", default="develop", help="Branch to start from and open the pull request into.")
    plan.add_argument("--model", default="sonnet", help="Model for the implementing agent (default: sonnet).")
    plan.add_argument("--depends-ok", action="store_true", help="Confirm the plan's dependencies are satisfied.")
    plan.add_argument("--no-ready", action="store_true", help="Leave the pull request a draft even if all is well.")

    ci = commands.add_parser("ci-status", help="Aggregate CI state for a commit.")
    ci.add_argument("--sha", default="HEAD", help="Commit to judge (default: HEAD).")
    _add_ci_arguments(ci)

    check = commands.add_parser("check-body", help="Check a readiness comment body before it is posted.")
    check.add_argument("--body-file", required=True, help="File holding the comment body.")
    baseline = check.add_mutually_exclusive_group()
    baseline.add_argument("--previous-pass", type=int, help="Pass number of the comment being replaced.")
    baseline.add_argument(
        "--edit-of",
        help="File holding the comment being edited: same pass, and only fixer status lines may be added.",
    )
    check.add_argument(
        "--forbid-env",
        action="append",
        default=[],
        help="Name of an environment variable whose value must not appear in the body; repeatable.",
    )
    return parser


def _print(value: object) -> None:
    print(json.dumps(value, indent=2))


def _pr_number(forge: Forge, requested: int | None) -> int:
    return requested if requested is not None else forge.pull_request(None).number


def _read_body(path: str) -> str:
    return sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")


def _pr_info(args: argparse.Namespace, forge: Forge) -> None:
    _print(forge.pull_request(args.pr).to_dict())


def _comment_get(args: argparse.Namespace, forge: Forge) -> None:
    comment = forge.find_comment(_pr_number(forge, args.pr), resolve_authors(forge, args.author))
    _print(None if comment is None else asdict(comment))


def _comment_upsert(args: argparse.Namespace, forge: Forge) -> None:
    number = _pr_number(forge, args.pr)
    comment, created = forge.upsert_comment(number, _read_body(args.body_file), resolve_authors(forge, args.author))
    _print({"id": comment.id, "action": "created" if created else "updated"})


def _ci_status(args: argparse.Namespace, forge: Forge) -> None:
    sha = git_output(get_repo_root(), "rev-parse", "HEAD").strip() if args.sha == "HEAD" else args.sha
    _print(asdict(wait_for_ci(forge, sha, args.exclude, args.wait)))


def _review_context(args: argparse.Namespace, forge: Forge) -> None:
    _print(
        review_context(
            forge,
            args.pr,
            args.author,
            args.exclude,
            args.wait,
            expected_sha=args.expect_sha,
            max_passes=args.max_passes,
        )
    )


def _check_body(args: argparse.Namespace, _forge: Forge) -> None:
    try:
        body = Path(args.body_file).read_text(encoding="utf-8")
    except FileNotFoundError:
        body = ""
    if not body.strip():
        raise ForgeError("The agent did not write a comment body.")
    forbidden = [os.environ.get(name, "") for name in args.forbid_env]
    if args.edit_of:
        try:
            old = Path(args.edit_of).read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise ForgeError(f"The comment being edited was not found: {args.edit_of}.") from exc
        old_pass = pass_number(old)
        if old_pass is None:
            raise ForgeError("The comment being edited has no pass header.")
        problems = body_problems(body, old_pass, forbidden, same_pass=True) + fixer_edit_problems(old, body)
    else:
        problems = body_problems(body, args.previous_pass, forbidden)
    if problems:
        raise ForgeError(" ".join(problems))
    _print({"ok": True})


def _fix_loop(args: argparse.Namespace, forge: Forge) -> None:
    git = LocalGit()
    git.require_clean_tree()
    with tempfile.TemporaryDirectory(prefix="fix-loop-") as work_dir:
        result = run_fix_loop(
            forge,
            git,
            functools.partial(run_claude_agent, model=args.model),
            email_notifier,
            Path(work_dir),
            args.pr,
            args.author,
            max_rounds=args.max_rounds,
            wait_seconds=args.wait_minutes * 60,
        )
    print(result_as_json(result))
    if result.outcome == "stopped":
        raise ForgeError(result.detail)


def _implement_plan(args: argparse.Namespace, forge: Forge) -> None:
    repo_root = get_repo_root()
    with tempfile.TemporaryDirectory(prefix="implement-plan-") as work_dir:
        result = run_implement_plan(
            forge,
            LocalGit(),
            functools.partial(run_claude_agent, model=args.model),
            run_gate,
            email_notifier,
            repo_root,
            Path(work_dir),
            Path(args.plan).name,
            depends_ok=args.depends_ok,
            base=args.base,
            mark_ready=not args.no_ready,
        )
    print(json.dumps(asdict(result), indent=2))
    if result.outcome in ("refused", "stopped"):
        raise ForgeError(result.detail)


COMMANDS: dict[str, Callable[[argparse.Namespace, Forge], None]] = {
    "pr-info": _pr_info,
    "comment-get": _comment_get,
    "comment-upsert": _comment_upsert,
    "ci-status": _ci_status,
    "review-context": _review_context,
    "check-body": _check_body,
    "fix-loop": _fix_loop,
    "implement-plan": _implement_plan,
}


def main(argv: Sequence[str] | None = None, forge: Forge | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        COMMANDS[args.command](args, forge or GitHubForge())
    except ForgeError as exc:
        print(f"forge: {exc}", file=sys.stderr)
        return 1
    return 0
