"""GitHub adapter: implements :class:`scripts.forge.base.Forge` by calling the ``gh`` CLI."""

import json
import subprocess
from collections.abc import Callable, Collection, Iterator, Sequence
from typing import Any

from common.git import get_repo_root
from scripts.forge.base import CheckRun, CiState, CiStatus, Comment, ForgeError, PullRequest, require_marker

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


def _classify(status: str, conclusion: str | None) -> CiState:
    if status != "completed":
        return "pending"
    return "pass" if conclusion in _PASSING_CONCLUSIONS else "fail"


def aggregate_ci_state(states: Collection[CiState]) -> CiState:
    """One state for a set of checks: any failure wins, then any pending, else pass; ``none`` when empty."""
    if not states:
        return "none"
    if "fail" in states:
        return "fail"
    if "pending" in states:
        return "pending"
    return "pass"


class GitHubForge:
    def __init__(self, runner: Runner = run_gh) -> None:
        self._run = runner

    def current_user(self) -> str:
        login = self._run(["api", "user", "--jq", ".login"], None).strip()
        if not login:
            raise ForgeError("Could not determine the authenticated GitHub user.")
        return login

    def pull_request(self, number: int | None) -> PullRequest:
        target = [] if number is None else [str(number)]
        data = json.loads(self._run(["pr", "view", *target, "--json", _PR_FIELDS], None))
        return PullRequest(
            number=data["number"],
            url=data["url"],
            base_ref=data["baseRefName"],
            head_ref=data["headRefName"],
            head_sha=data["headRefOid"],
            is_draft=data["isDraft"],
            state=data["state"],
        )

    def find_comment(self, number: int, marker: str, authors: Collection[str]) -> Comment | None:
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
        for item in _json_values(output):
            if item["author"] in authors and item["body"].startswith(marker):
                return Comment(id=item["id"], body=item["body"], author=item["author"])
        return None

    def upsert_comment(self, number: int, marker: str, body: str, authors: Collection[str]) -> tuple[Comment, bool]:
        require_marker(body, marker)
        existing = self.find_comment(number, marker, authors)
        payload = json.dumps({"body": body})
        if existing is None:
            path, method = f"repos/{{owner}}/{{repo}}/issues/{number}/comments", "POST"
        else:
            path, method = f"repos/{{owner}}/{{repo}}/issues/comments/{existing.id}", "PATCH"
        saved = json.loads(self._run(["api", "-X", method, path, "--input", "-"], payload))
        comment = Comment(id=saved["id"], body=saved["body"], author=saved["user"]["login"])
        return comment, existing is None

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
        checks = tuple(
            CheckRun(name=item["name"], state=_classify(item["status"], item["conclusion"]))
            for item in _json_values(output)
            if item["name"] not in exclude
        )
        return CiStatus(sha=sha, state=aggregate_ci_state([check.state for check in checks]), checks=checks)
