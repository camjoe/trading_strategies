"""Command line for the forge interface: ``python -m scripts.forge <operation>``.

Every operation prints JSON on stdout. A failed operation prints ``forge: <reason>`` on stderr and
exits 1. The only comment this tool writes is the readiness comment (``<!-- pr-readiness -->``).
"""

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

from common.git import get_repo_root, git_output
from scripts.forge.base import READINESS_MARKER, Forge, ForgeError
from scripts.forge.github import GitHubForge
from scripts.forge.service import resolve_authors, review_context, wait_for_ci


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m scripts.forge", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    pr_info = commands.add_parser("pr-info", help="Pull request number, refs, head sha, draft flag, state.")
    pr_info.add_argument("--pr", type=int, help="Pull request number (default: the current branch's).")

    for name, help_text in (
        ("comment-get", "The readiness comment, or null."),
        ("comment-upsert", "Create or edit the readiness comment from a file."),
        ("review-context", "Pull request, previous readiness comment, and CI state in one answer."),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("--pr", type=int, help="Pull request number (default: the current branch's).")
        command.add_argument(
            "--author",
            action="append",
            default=[],
            help="Trusted comment author; repeatable (default: the authenticated user).",
        )
        if name == "comment-upsert":
            command.add_argument("--body-file", required=True, help="File holding the comment body, or - for stdin.")
        if name == "review-context":
            _add_ci_arguments(command)

    ci = commands.add_parser("ci-status", help="Aggregate CI state for a commit.")
    ci.add_argument("--sha", default="HEAD", help="Commit to judge (default: HEAD).")
    _add_ci_arguments(ci)
    return parser


def _add_ci_arguments(command: argparse.ArgumentParser) -> None:
    command.add_argument("--exclude", action="append", default=[], help="Check name to ignore; repeatable.")
    command.add_argument("--wait", type=float, default=0, help="Seconds to wait for pending checks (default: 0).")


def _print(value: object) -> None:
    print(json.dumps(value, indent=2))


def _pr_number(forge: Forge, requested: int | None) -> int:
    return forge.pull_request(requested).number


def run(args: argparse.Namespace, forge: Forge) -> int:
    if args.command == "pr-info":
        pr = forge.pull_request(args.pr)
        _print({**asdict(pr), "diff_base_ref": pr.diff_base_ref})
    elif args.command == "comment-get":
        number = _pr_number(forge, args.pr)
        comment = forge.find_comment(number, READINESS_MARKER, resolve_authors(forge, args.author))
        _print(None if comment is None else asdict(comment))
    elif args.command == "comment-upsert":
        number = _pr_number(forge, args.pr)
        body_path = args.body_file
        body = sys.stdin.read() if body_path == "-" else Path(body_path).read_text(encoding="utf-8")
        comment, created = forge.upsert_comment(number, READINESS_MARKER, body, resolve_authors(forge, args.author))
        _print({"id": comment.id, "action": "created" if created else "updated"})
    elif args.command == "ci-status":
        sha = git_output(get_repo_root(), "rev-parse", "HEAD").strip() if args.sha == "HEAD" else args.sha
        _print(asdict(wait_for_ci(forge, sha, args.exclude, args.wait)))
    else:
        _print(review_context(forge, args.pr, args.author, args.exclude, args.wait))
    return 0


def main(argv: Sequence[str] | None = None, forge: Forge | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run(args, forge or GitHubForge())
    except ForgeError as exc:
        print(f"forge: {exc}", file=sys.stderr)
        return 1
