"""GitHub adapter: implements :class:`scripts.forge.base.Forge` by calling the ``gh`` CLI."""

import json
import re
import subprocess
from collections.abc import Callable, Collection, Iterator, Sequence
from contextlib import contextmanager
from typing import Any

from common.git import get_repo_root
from scripts.forge.base import (
    READINESS_MARKER,
    CheckRun,
    CiState,
    CiStatus,
    Comment,
    ForgeError,
    InlineComment,
    PullRequest,
    aggregate_ci_state,
    finding_marker_number,
    require_finding_marker,
    require_marker,
)

Runner = Callable[[Sequence[str], str | None], str]

_PR_FIELDS = "number,url,baseRefName,headRefName,headRefOid,isDraft,state"
_PASSING_CONCLUSIONS = {"success", "neutral", "skipped"}


def run_gh(args: Sequence[str], stdin: str | None = None) -> str:
    """Run ``gh <args>`` from the repository root and return stdout."""
    try:
        completed = subprocess.run(
            ["gh", *args],
            cwd=get_repo_root(),
            input=stdin,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError as exc:
        raise ForgeError("The gh CLI is not installed or not on PATH.") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or "").strip() or f"exit status {exc.returncode}"
        raise ForgeError(f"gh {' '.join(args[:2])} failed: {detail}") from exc
    return completed.stdout


@contextmanager
def _expect_shape(what: str) -> Iterator[None]:
    """Turn a malformed ``gh`` reply into a :class:`ForgeError` instead of a traceback."""
    try:
        yield
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        raise ForgeError(f"Unexpected gh output for {what}.") from exc


def _json_values(text: str) -> Iterator[Any]:
    """Yield each JSON value in *text*, which may be several concatenated documents."""
    decoder = json.JSONDecoder()
    index = 0
    while index < len(text):
        if text[index].isspace():
            index += 1
            continue
        value, index = decoder.raw_decode(text, index)
        yield value


_HUNK_START = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")

_THREADS_QUERY = """
query($owner: String!, $name: String!, $number: Int!, $endCursor: String) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      reviewThreads(first: 100, after: $endCursor) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id isResolved isOutdated
          comments(first: 1) { totalCount nodes { databaseId body path line author { login } } }
        }
      }
    }
  }
}
"""

_RESOLVE_MUTATION = """
mutation($threadId: ID!) {
  resolveReviewThread(input: {threadId: $threadId}) { thread { isResolved } }
}
"""


def _login(name: str) -> str:
    """A login without the ``[bot]`` suffix: REST spells a bot ``github-actions[bot]``, GraphQL ``github-actions``."""
    return name.removesuffix("[bot]")


def new_side_lines(patch: str) -> frozenset[int]:
    """The new-side line numbers a unified-diff *patch* shows: added lines and unchanged context lines."""
    lines: set[int] = set()
    new_line = 0
    for text in patch.splitlines():
        start = _HUNK_START.match(text)
        if start:
            new_line = int(start.group(1))
        elif new_line and text.startswith(("+", " ")):
            lines.add(new_line)
            new_line += 1
    return frozenset(lines)


def _classify(status: str, conclusion: str | None) -> CiState:
    if status != "completed":
        return "pending"
    return "pass" if conclusion in _PASSING_CONCLUSIONS else "fail"


class GitHubForge:
    def __init__(self, runner: Runner = run_gh) -> None:
        self._run = runner

    def current_user(self) -> str:
        login = self._run(["api", "user", "--jq", ".login"], None).strip()
        if not login:
            raise ForgeError("Could not determine the authenticated GitHub user.")
        return login

    def pull_request(self, number: int | None) -> PullRequest:
        return self._view([] if number is None else [str(number)])

    def _view(self, target: list[str]) -> PullRequest:
        output = self._run(["pr", "view", *target, "--json", _PR_FIELDS], None)
        with _expect_shape("pr view"):
            data = json.loads(output)
            return PullRequest(
                number=data["number"],
                url=data["url"],
                base_ref=data["baseRefName"],
                head_ref=data["headRefName"],
                head_sha=data["headRefOid"],
                is_draft=data["isDraft"],
                state=data["state"],
            )

    def open_pull_request(self, base: str, head: str, title: str, body: str, draft: bool = True) -> PullRequest:
        args = ["pr", "create", "--base", base, "--head", head, "--title", title, "--body-file", "-"]
        output = self._run([*args, *(["--draft"] if draft else [])], body)
        with _expect_shape("pr create"):
            number = int(output.strip().splitlines()[-1].rstrip("/").rsplit("/", 1)[1])
        return self.pull_request(number)

    def set_ready(self, number: int) -> None:
        self._run(["pr", "ready", str(number)], None)

    def set_pull_request_body(self, number: int, body: str) -> None:
        self._run(["pr", "edit", str(number), "--body-file", "-"], body)

    def find_comment(self, number: int, authors: Collection[str]) -> Comment | None:
        output = self._run(
            [
                "api",
                f"repos/{{owner}}/{{repo}}/issues/{number}/comments",
                "--paginate",
                "--jq",
                ".[] | {id: .id, body: .body, author: .user.login}",
            ],
            None,
        )
        with _expect_shape("issue comments"):
            for item in _json_values(output):
                if item["author"] in authors and item["body"].startswith(READINESS_MARKER):
                    return Comment(id=item["id"], body=item["body"], author=item["author"])
        return None

    def upsert_comment(self, number: int, body: str, authors: Collection[str]) -> tuple[Comment, bool]:
        require_marker(body)
        existing = self.find_comment(number, authors)
        payload = json.dumps({"body": body})
        if existing is None:
            path, method = f"repos/{{owner}}/{{repo}}/issues/{number}/comments", "POST"
        else:
            path, method = f"repos/{{owner}}/{{repo}}/issues/comments/{existing.id}", "PATCH"
        output = self._run(["api", "-X", method, path, "--input", "-"], payload)
        with _expect_shape("comment write"):
            saved = json.loads(output)
            comment = Comment(id=saved["id"], body=saved["body"], author=saved["user"]["login"])
        return comment, existing is None

    def _repository(self) -> tuple[str, str]:
        name = self._run(["repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"], None).strip()
        owner, _, repo = name.partition("/")
        if not owner or not repo:
            raise ForgeError("Could not determine the repository owner and name.")
        return owner, repo

    def diff_lines(self, number: int) -> dict[str, frozenset[int]]:
        output = self._run(
            [
                "api",
                f"repos/{{owner}}/{{repo}}/pulls/{number}/files",
                "--paginate",
                "--jq",
                '.[] | {filename: .filename, patch: (.patch // "")}',
            ],
            None,
        )
        with _expect_shape("pull request files"):
            return {item["filename"]: new_side_lines(item["patch"]) for item in _json_values(output)}

    def inline_comments(self, number: int, authors: Collection[str]) -> list[InlineComment]:
        owner, repo = self._repository()
        output = self._run(
            [
                "api",
                "graphql",
                "--paginate",
                "-f",
                f"query={_THREADS_QUERY}",
                "-f",
                f"owner={owner}",
                "-f",
                f"name={repo}",
                "-F",
                f"number={number}",
                "--jq",
                ".data.repository.pullRequest.reviewThreads.nodes[] | {thread: .id, resolved: .isResolved, "
                "outdated: .isOutdated, replies: (.comments.totalCount - 1), comment: .comments.nodes[0]}",
            ],
            None,
        )
        comments: list[InlineComment] = []
        names = {_login(author) for author in authors}
        with _expect_shape("review threads"):
            for item in _json_values(output):
                comment = item["comment"]
                author = comment["author"] if comment else None
                if author is None or _login(author["login"]) not in names:
                    continue
                found = InlineComment(
                    id=comment["databaseId"],
                    thread_id=item["thread"],
                    body=comment["body"],
                    author=author["login"],
                    path=comment["path"],
                    line=comment["line"],
                    resolved=item["resolved"],
                    outdated=item["outdated"],
                    reply_count=int(item["replies"]),
                )
                if found.finding_number is not None:
                    comments.append(found)
        return comments

    def repository(self) -> str:
        owner, repo = self._repository()
        return f"{owner}/{repo}"

    def merged_pull_requests(self, limit: int) -> list[int]:
        output = self._run(
            ["pr", "list", "--state", "merged", "--limit", str(limit), "--json", "number", "--jq", ".[].number"], None
        )
        with _expect_shape("merged pull requests"):
            return [int(line) for line in output.split()]

    def finding_reactions(self, number: int, authors: Collection[str]) -> dict[int, tuple[int, int]]:
        output = self._run(
            [
                "api",
                f"repos/{{owner}}/{{repo}}/pulls/{number}/comments",
                "--paginate",
                "--jq",
                ".[] | select(.in_reply_to_id == null) | "
                '{id: .id, author: .user.login, body: .body, up: .reactions["+1"], down: .reactions["-1"]}',
            ],
            None,
        )
        names = {_login(author) for author in authors}
        latest: dict[int, tuple[int, int, int]] = {}
        with _expect_shape("review comments"):
            for item in _json_values(output):
                found = finding_marker_number(item["body"])
                if found is not None and _login(item["author"]) in names and item["id"] > latest.get(found, (0,))[0]:
                    latest[found] = (item["id"], int(item["up"]), int(item["down"]))
        return {found: (up, down) for found, (_, up, down) in latest.items()}

    def create_inline_comment(self, number: int, head_sha: str, path: str, line: int, body: str) -> int:
        require_finding_marker(body)
        payload = json.dumps({"body": body, "commit_id": head_sha, "path": path, "line": line, "side": "RIGHT"})
        output = self._run(
            ["api", "-X", "POST", f"repos/{{owner}}/{{repo}}/pulls/{number}/comments", "--input", "-"], payload
        )
        with _expect_shape("review comment write"):
            return int(json.loads(output)["id"])

    def reply_to_inline_comment(self, number: int, comment_id: int, body: str) -> None:
        require_finding_marker(body)
        self._run(
            [
                "api",
                "-X",
                "POST",
                f"repos/{{owner}}/{{repo}}/pulls/{number}/comments/{comment_id}/replies",
                "--input",
                "-",
            ],
            json.dumps({"body": body}),
        )

    def edit_inline_comment(self, comment_id: int, body: str) -> None:
        require_finding_marker(body)
        self._run(
            ["api", "-X", "PATCH", f"repos/{{owner}}/{{repo}}/pulls/comments/{comment_id}", "--input", "-"],
            json.dumps({"body": body}),
        )

    def resolve_thread(self, thread_id: str) -> None:
        self._run(["api", "graphql", "-f", f"query={_RESOLVE_MUTATION}", "-f", f"threadId={thread_id}"], None)

    def ci_status(self, sha: str, exclude: Collection[str] = ()) -> CiStatus:
        output = self._run(
            [
                "api",
                f"repos/{{owner}}/{{repo}}/commits/{sha}/check-runs",
                "--paginate",
                "--jq",
                ".check_runs[] | {name: .name, status: .status, conclusion: .conclusion}",
            ],
            None,
        )
        with _expect_shape("check runs"):
            checks = tuple(
                CheckRun(name=item["name"], state=_classify(item["status"], item["conclusion"]))
                for item in _json_values(output)
                if item["name"] not in exclude
            )
        return CiStatus(sha=sha, state=aggregate_ci_state([check.state for check in checks]), checks=checks)
