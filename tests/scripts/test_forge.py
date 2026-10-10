import json
import subprocess
from collections.abc import Collection, Sequence
from pathlib import Path

import pytest

from scripts.forge import github as github_module
from scripts.forge.base import (
    READINESS_MARKER,
    CheckRun,
    CiStatus,
    Comment,
    ForgeError,
    PullRequest,
    require_marker,
)
from scripts.forge.cli import main
from scripts.forge.github import GitHubForge, aggregate_ci_state
from scripts.forge.service import resolve_authors, review_context, wait_for_ci

PR_JSON = {
    "number": 7,
    "url": "https://example.test/pull/7",
    "baseRefName": "develop",
    "headRefName": "feature/x",
    "headRefOid": "abc123",
    "isDraft": False,
    "state": "OPEN",
}


class FakeRunner:
    """Stands in for ``gh``: returns canned output for the first matching argument fragment."""

    def __init__(self, responses: dict[str, str]) -> None:
        self.responses = responses
        self.calls: list[tuple[list[str], str | None]] = []

    def __call__(self, args: Sequence[str], stdin: str | None = None) -> str:
        self.calls.append((list(args), stdin))
        joined = " ".join(args)
        for fragment, output in self.responses.items():
            if fragment in joined:
                return output
        raise AssertionError(f"unexpected gh call: {joined}")


def comment_lines(*items: dict[str, object]) -> str:
    return "\n".join(json.dumps(item) for item in items)


def readiness(author: str = "bot", comment_id: int = 1) -> dict[str, object]:
    return {"id": comment_id, "body": f"{READINESS_MARKER}\nbody", "author": author}


class TestRequireMarker:
    def test_accepts_a_body_that_starts_with_the_marker(self) -> None:
        require_marker(f"{READINESS_MARKER}\ntext", READINESS_MARKER)

    def test_refuses_any_other_body(self) -> None:
        with pytest.raises(ForgeError, match="must start with"):
            require_marker("some other comment", READINESS_MARKER)


class TestAggregateCiState:
    def test_no_checks_is_none(self) -> None:
        assert aggregate_ci_state([]) == "none"

    def test_failure_beats_pending(self) -> None:
        assert aggregate_ci_state(["pass", "pending", "fail"]) == "fail"

    def test_pending_beats_pass(self) -> None:
        assert aggregate_ci_state(["pass", "pending"]) == "pending"

    def test_all_passing_is_pass(self) -> None:
        assert aggregate_ci_state(["pass", "pass"]) == "pass"


class TestGitHubForge:
    def test_pull_request_maps_fields_and_names_the_remote_base(self) -> None:
        runner = FakeRunner({"pr view 7": json.dumps(PR_JSON)})

        pr = GitHubForge(runner).pull_request(7)

        assert pr == PullRequest(7, "https://example.test/pull/7", "develop", "feature/x", "abc123", False, "OPEN")
        assert pr.diff_base_ref == "origin/develop"

    def test_pull_request_without_a_number_uses_the_current_branch(self) -> None:
        runner = FakeRunner({"pr view": json.dumps(PR_JSON)})

        GitHubForge(runner).pull_request(None)

        assert runner.calls[0][0][:2] == ["pr", "view"]
        assert runner.calls[0][0][2] == "--json"

    def test_find_comment_ignores_marker_comments_from_untrusted_authors(self) -> None:
        output = comment_lines(readiness("stranger", 1), readiness("bot", 2))
        forge = GitHubForge(FakeRunner({"issues/7/comments": output}))

        comment = forge.find_comment(7, READINESS_MARKER, ["bot"])

        assert comment is not None
        assert (comment.id, comment.author) == (2, "bot")

    def test_find_comment_ignores_trusted_comments_without_the_marker(self) -> None:
        output = comment_lines({"id": 3, "body": "hello", "author": "bot"})
        forge = GitHubForge(FakeRunner({"issues/7/comments": output}))

        assert forge.find_comment(7, READINESS_MARKER, ["bot"]) is None

    def test_find_comment_reads_pretty_printed_json(self) -> None:
        pretty = json.dumps(readiness("bot", 5), indent=2) + "\n" + json.dumps(readiness("bot", 6), indent=2)
        forge = GitHubForge(FakeRunner({"issues/7/comments": pretty}))

        comment = forge.find_comment(7, READINESS_MARKER, ["bot"])

        assert comment is not None
        assert comment.id == 5

    def test_upsert_creates_when_no_comment_exists(self) -> None:
        saved = {"id": 9, "body": f"{READINESS_MARKER}\nnew", "user": {"login": "bot"}}
        runner = FakeRunner({"-X POST": json.dumps(saved), "issues/7/comments --paginate": ""})

        comment, created = GitHubForge(runner).upsert_comment(7, READINESS_MARKER, f"{READINESS_MARKER}\nnew", ["bot"])

        assert created is True
        assert comment.id == 9
        method_call = runner.calls[-1]
        assert method_call[0][:3] == ["api", "-X", "POST"]
        assert json.loads(method_call[1] or "") == {"body": f"{READINESS_MARKER}\nnew"}

    def test_upsert_edits_the_existing_comment_in_place(self) -> None:
        saved = {"id": 2, "body": f"{READINESS_MARKER}\nv2", "user": {"login": "bot"}}
        runner = FakeRunner(
            {"-X PATCH": json.dumps(saved), "issues/7/comments --paginate": comment_lines(readiness())}
        )

        comment, created = GitHubForge(runner).upsert_comment(7, READINESS_MARKER, f"{READINESS_MARKER}\nv2", ["bot"])

        assert created is False
        assert comment.id == 2
        patch_call = runner.calls[-1]
        assert patch_call[0][:4] == ["api", "-X", "PATCH", "repos/{owner}/{repo}/issues/comments/1"]

    def test_upsert_refuses_a_body_without_the_marker_before_calling_gh(self) -> None:
        runner = FakeRunner({})

        with pytest.raises(ForgeError, match="must start with"):
            GitHubForge(runner).upsert_comment(7, READINESS_MARKER, "not the marker", ["bot"])

        assert runner.calls == []

    def test_ci_status_aggregates_and_excludes_named_checks(self) -> None:
        output = comment_lines(
            {"name": "python", "status": "completed", "conclusion": "success"},
            {"name": "review", "status": "in_progress", "conclusion": None},
            {"name": "docs", "status": "completed", "conclusion": "skipped"},
        )
        forge = GitHubForge(FakeRunner({"check-runs": output}))

        assert forge.ci_status("abc", exclude=["review"]).state == "pass"
        assert forge.ci_status("abc").state == "pending"

    def test_ci_status_treats_cancelled_and_failed_as_fail(self) -> None:
        output = comment_lines({"name": "python", "status": "completed", "conclusion": "cancelled"})
        forge = GitHubForge(FakeRunner({"check-runs": output}))

        assert forge.ci_status("abc").state == "fail"

    def test_ci_status_with_no_checks_is_none(self) -> None:
        assert GitHubForge(FakeRunner({"check-runs": ""})).ci_status("abc").state == "none"

    def test_current_user_requires_a_login(self) -> None:
        with pytest.raises(ForgeError, match="authenticated"):
            GitHubForge(FakeRunner({"api user": "\n"})).current_user()


class TestRunGh:
    def test_failure_becomes_a_forge_error_with_the_stderr(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def fail(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
            raise subprocess.CalledProcessError(1, "gh", stderr="HTTP 404\n")

        monkeypatch.setattr(github_module, "get_repo_root", lambda: Path("."))
        monkeypatch.setattr(github_module.subprocess, "run", fail)

        with pytest.raises(ForgeError, match="HTTP 404"):
            github_module.run_gh(["api", "x"])

    def test_missing_gh_becomes_a_forge_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def missing(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
            raise FileNotFoundError

        monkeypatch.setattr(github_module, "get_repo_root", lambda: Path("."))
        monkeypatch.setattr(github_module.subprocess, "run", missing)

        with pytest.raises(ForgeError, match="not installed"):
            github_module.run_gh(["api", "x"])


class StubForge:
    """A forge with fixed answers, recording the CI polls."""

    def __init__(
        self,
        previous: Comment | None = None,
        ci_states: Sequence[str] = ("pass",),
        user: str | None = "me",
    ) -> None:
        self.previous = previous
        self.ci_states = list(ci_states)
        self.user = user
        self.ci_polls = 0
        self.find_authors: Collection[str] = ()
        self.upserted: list[str] = []

    def current_user(self) -> str:
        if self.user is None:
            raise ForgeError("no user")
        return self.user

    def pull_request(self, number: int | None) -> PullRequest:
        return PullRequest(number or 7, "u", "develop", "feature/x", "abc123", False, "OPEN")

    def find_comment(self, number: int, marker: str, authors: Collection[str]) -> Comment | None:
        self.find_authors = authors
        return self.previous

    def upsert_comment(self, number: int, marker: str, body: str, authors: Collection[str]) -> tuple[Comment, bool]:
        require_marker(body, marker)
        self.upserted.append(body)
        return Comment(id=11, body=body, author="me"), self.previous is None

    def ci_status(self, sha: str, exclude: Collection[str] = ()) -> CiStatus:
        state = self.ci_states[min(self.ci_polls, len(self.ci_states) - 1)]
        self.ci_polls += 1
        return CiStatus(sha=sha, state=state, checks=(CheckRun("python", state),))  # type: ignore[arg-type]


class TestService:
    def test_resolve_authors_prefers_the_given_authors(self) -> None:
        assert resolve_authors(StubForge(), ["bot"]) == ("bot",)

    def test_resolve_authors_falls_back_to_the_authenticated_user(self) -> None:
        assert resolve_authors(StubForge(user="me"), []) == ("me",)

    def test_resolve_authors_fails_when_no_trusted_author_is_known(self) -> None:
        with pytest.raises(ForgeError, match="pass --author"):
            resolve_authors(StubForge(user=None), [])

    def test_wait_for_ci_polls_until_checks_settle(self) -> None:
        forge = StubForge(ci_states=["pending", "pending", "pass"])
        now = [0.0]

        status = wait_for_ci(
            forge,
            "abc",
            timeout_seconds=100,
            interval_seconds=10,
            sleep=lambda s: now.__setitem__(0, now[0] + s),
            clock=lambda: now[0],
        )

        assert status.state == "pass"
        assert forge.ci_polls == 3

    def test_wait_for_ci_gives_up_at_the_timeout_and_reports_pending(self) -> None:
        forge = StubForge(ci_states=["pending"])
        now = [0.0]

        status = wait_for_ci(
            forge,
            "abc",
            timeout_seconds=25,
            interval_seconds=10,
            sleep=lambda s: now.__setitem__(0, now[0] + s),
            clock=lambda: now[0],
        )

        assert status.state == "pending"

    def test_wait_for_ci_does_not_poll_again_with_no_timeout(self) -> None:
        forge = StubForge(ci_states=["pending", "pass"])

        assert wait_for_ci(forge, "abc").state == "pending"
        assert forge.ci_polls == 1

    def test_review_context_bundles_pull_request_previous_comment_and_ci(self) -> None:
        previous = Comment(id=3, body=f"{READINESS_MARKER}\nold", author="bot")
        forge = StubForge(previous=previous)

        context = review_context(forge, 7, ["bot"])

        assert context["pull_request"]["diff_base_ref"] == "origin/develop"
        assert context["pull_request"]["head_sha"] == "abc123"
        assert context["previous_comment"]["body"].endswith("old")
        assert context["ci"]["state"] == "pass"
        assert forge.find_authors == ("bot",)

    def test_review_context_first_pass_has_no_previous_comment(self) -> None:
        assert review_context(StubForge(), None, [])["previous_comment"] is None


class TestCli:
    def test_pr_info_prints_json(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert main(["pr-info", "--pr", "7"], StubForge()) == 0

        printed = json.loads(capsys.readouterr().out)
        assert printed["number"] == 7
        assert printed["diff_base_ref"] == "origin/develop"

    def test_comment_get_prints_null_when_absent(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert main(["comment-get", "--pr", "7"], StubForge()) == 0

        assert json.loads(capsys.readouterr().out) is None

    def test_comment_upsert_reads_the_body_file(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        body = tmp_path / "body.md"
        body.write_text(f"{READINESS_MARKER}\ntext", encoding="utf-8")
        forge = StubForge()

        assert main(["comment-upsert", "--pr", "7", "--body-file", str(body)], forge) == 0

        assert json.loads(capsys.readouterr().out) == {"id": 11, "action": "created"}
        assert forge.upserted == [f"{READINESS_MARKER}\ntext"]

    def test_comment_upsert_refuses_a_body_without_the_marker(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        body = tmp_path / "body.md"
        body.write_text("not a readiness comment", encoding="utf-8")

        assert main(["comment-upsert", "--pr", "7", "--body-file", str(body)], StubForge()) == 1

        assert "must start with" in capsys.readouterr().err

    def test_review_context_prints_one_json_document(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert main(["review-context", "--pr", "7", "--author", "bot"], StubForge()) == 0

        printed = json.loads(capsys.readouterr().out)
        assert set(printed) == {"pull_request", "previous_comment", "ci"}

    def test_a_forge_error_prints_to_stderr_and_exits_one(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert main(["comment-get", "--pr", "7"], StubForge(user=None)) == 1

        assert capsys.readouterr().err.startswith("forge: ")

    def test_ci_status_accepts_an_explicit_sha(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert main(["ci-status", "--sha", "deadbeef"], StubForge()) == 0

        assert json.loads(capsys.readouterr().out)["sha"] == "deadbeef"
