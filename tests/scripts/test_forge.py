import json
import subprocess
from collections.abc import Collection, Sequence
from io import StringIO
from pathlib import Path

import pytest

from scripts.forge import cli as cli_module, github as github_module, service as service_module
from scripts.forge.base import (
    READINESS_MARKER,
    CheckRun,
    CiState,
    CiStatus,
    Comment,
    ForgeError,
    PullRequest,
    aggregate_ci_state,
    require_marker,
)
from scripts.forge.cli import main
from scripts.forge.github import GitHubForge
from scripts.forge.readiness import body_problems, fixer_edit_problems, pass_number
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


def readiness_body(pass_no: int = 1, extra: str = "") -> str:
    return f"{READINESS_MARKER}\n## PR readiness: NOT READY\n\nReviewed `abc` · 2026-10-10 · pass {pass_no} · current\n{extra}"


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


def json_lines(*items: dict[str, object]) -> str:
    return "\n".join(json.dumps(item) for item in items)


def comment_item(author: str = "bot", comment_id: int = 1, body: str | None = None) -> dict[str, object]:
    return {"id": comment_id, "body": body or readiness_body(), "author": author}


def check_item(name: str, status: str = "completed", conclusion: str | None = "success") -> dict[str, object]:
    return {"name": name, "status": status, "conclusion": conclusion}


class TestRequireMarker:
    def test_accepts_a_body_that_starts_with_the_marker(self) -> None:
        require_marker(f"{READINESS_MARKER}\ntext")

    def test_refuses_any_other_body(self) -> None:
        with pytest.raises(ForgeError, match="must start with"):
            require_marker("some other comment")


class TestAggregateCiState:
    def test_no_checks_is_none(self) -> None:
        assert aggregate_ci_state([]) == "none"

    def test_failure_beats_pending(self) -> None:
        assert aggregate_ci_state(["pass", "pending", "fail"]) == "fail"

    def test_pending_beats_pass(self) -> None:
        assert aggregate_ci_state(["pass", "pending"]) == "pending"

    def test_all_passing_is_pass(self) -> None:
        assert aggregate_ci_state(["pass", "pass"]) == "pass"


class TestReadiness:
    def test_pass_number_reads_the_header(self) -> None:
        assert pass_number(readiness_body(3)) == 3

    def test_pass_number_is_none_without_a_header(self) -> None:
        assert pass_number(f"{READINESS_MARKER}\nno header") is None

    def test_a_good_first_pass_has_no_problems(self) -> None:
        assert body_problems(readiness_body(1), None) == []

    def test_a_good_later_pass_has_no_problems(self) -> None:
        assert body_problems(readiness_body(3), 2) == []

    def test_a_pass_that_is_not_previous_plus_one_is_a_problem(self) -> None:
        assert any("should say pass 3" in problem for problem in body_problems(readiness_body(1), 2))

    def test_a_first_pass_must_say_pass_one(self) -> None:
        assert any("should say pass 1" in problem for problem in body_problems(readiness_body(4), None))

    def test_a_missing_marker_is_a_problem(self) -> None:
        body = readiness_body(1).removeprefix(READINESS_MARKER)

        assert any("must start with" in problem for problem in body_problems(body, None))

    @pytest.mark.parametrize(
        "text",
        ["see /home/runner/work/x", "at /Users/someone/repo", "ends with `/Users/someone`", r"at C:\Users\someone"],
    )
    def test_a_local_path_is_a_problem(self, text: str) -> None:
        assert any("local path" in p for p in body_problems(readiness_body(1, text), None))

    def test_text_that_only_names_a_path_prefix_is_fine(self) -> None:
        body = readiness_body(1, "The `/Users/` and `/home/runner` patterns have no test.")

        assert body_problems(body, None) == []

    def test_a_github_token_is_a_problem(self) -> None:
        assert any("credential" in p for p in body_problems(readiness_body(1, "ghp_" + "a" * 24), None))

    def test_the_first_header_line_wins_when_several_say_pass(self) -> None:
        body = f"{READINESS_MARKER}\nReviewed `a` · 2026-10-10 · pass 3 · current\nReviewed `b` · 2026-10-10 · pass 7 · current\n"

        assert pass_number(body) == 3

    def test_a_stray_pass_mention_before_the_header_does_not_win(self) -> None:
        body = f"{READINESS_MARKER}\nnote: see pass 9 below\nReviewed `abc` · 2026-10-10 · pass 2 · current\n"

        assert pass_number(body) == 2

    def test_a_forbidden_string_is_a_problem(self) -> None:
        assert any(
            "forbidden" in p for p in body_problems(readiness_body(1, "value s3cr3t"), None, forbidden=["s3cr3t"])
        )

    def test_an_empty_forbidden_string_is_a_problem(self) -> None:
        assert any("empty" in p for p in body_problems(readiness_body(1), None, forbidden=[""]))

    def test_credential_like_text_is_a_problem(self) -> None:
        assert any(
            "credential" in problem for problem in body_problems(readiness_body(1, "sk-ant-abcdefghij12345"), None)
        )


class TestGitHubForge:
    def test_pull_request_maps_fields_and_names_the_remote_base(self) -> None:
        runner = FakeRunner({"pr view 7": json.dumps(PR_JSON)})

        pr = GitHubForge(runner).pull_request(7)

        assert pr == PullRequest(7, "https://example.test/pull/7", "develop", "feature/x", "abc123", False, "OPEN")
        assert pr.to_dict()["diff_base_ref"] == "origin/develop"

    def test_pull_request_without_a_number_uses_the_current_branch(self) -> None:
        runner = FakeRunner({"pr view": json.dumps(PR_JSON)})

        GitHubForge(runner).pull_request(None)

        assert runner.calls[0][0][:3] == ["pr", "view", "--json"]

    def test_find_comment_ignores_marker_comments_from_untrusted_authors(self) -> None:
        output = json_lines(comment_item("stranger", 1), comment_item("bot", 2))
        forge = GitHubForge(FakeRunner({"issues/7/comments": output}))

        comment = forge.find_comment(7, ["bot"])

        assert comment is not None
        assert (comment.id, comment.author) == (2, "bot")

    def test_find_comment_ignores_trusted_comments_without_the_marker(self) -> None:
        forge = GitHubForge(FakeRunner({"issues/7/comments": json_lines(comment_item("bot", 3, "hello"))}))

        assert forge.find_comment(7, ["bot"]) is None

    def test_find_comment_reads_pretty_printed_json(self) -> None:
        pretty = json.dumps(comment_item("bot", 5), indent=2) + "\n" + json.dumps(comment_item("bot", 6), indent=2)
        forge = GitHubForge(FakeRunner({"issues/7/comments": pretty}))

        comment = forge.find_comment(7, ["bot"])

        assert comment is not None
        assert comment.id == 5

    def test_upsert_creates_when_no_comment_exists(self) -> None:
        body = readiness_body()
        saved = {"id": 9, "body": body, "user": {"login": "bot"}}
        runner = FakeRunner({"-X POST": json.dumps(saved), "issues/7/comments --paginate": ""})

        comment, created = GitHubForge(runner).upsert_comment(7, body, ["bot"])

        assert created is True
        assert comment.id == 9
        method_call = runner.calls[-1]
        assert method_call[0][:3] == ["api", "-X", "POST"]
        assert json.loads(method_call[1] or "") == {"body": body}

    def test_upsert_edits_the_existing_comment_in_place(self) -> None:
        body = readiness_body(2)
        saved = {"id": 1, "body": body, "user": {"login": "bot"}}
        runner = FakeRunner(
            {"-X PATCH": json.dumps(saved), "issues/7/comments --paginate": json_lines(comment_item("bot", 1))}
        )

        comment, created = GitHubForge(runner).upsert_comment(7, body, ["bot"])

        assert created is False
        assert comment.id == 1
        assert runner.calls[-1][0][:4] == ["api", "-X", "PATCH", "repos/{owner}/{repo}/issues/comments/1"]

    def test_upsert_creates_a_new_comment_when_only_a_stranger_has_one(self) -> None:
        body = readiness_body()
        saved = {"id": 9, "body": body, "user": {"login": "bot"}}
        runner = FakeRunner(
            {"-X POST": json.dumps(saved), "issues/7/comments --paginate": json_lines(comment_item("stranger", 1))}
        )

        _, created = GitHubForge(runner).upsert_comment(7, body, ["bot"])

        assert created is True
        assert all("PATCH" not in call[0] for call in runner.calls)

    def test_upsert_refuses_a_body_without_the_marker_before_calling_gh(self) -> None:
        runner = FakeRunner({})

        with pytest.raises(ForgeError, match="must start with"):
            GitHubForge(runner).upsert_comment(7, "not the marker", ["bot"])

        assert runner.calls == []

    def test_ci_status_aggregates_and_excludes_named_checks(self) -> None:
        output = json_lines(
            check_item("python"),
            check_item("review", status="in_progress", conclusion=None),
            check_item("docs", conclusion="skipped"),
        )
        forge = GitHubForge(FakeRunner({"check-runs": output}))

        assert forge.ci_status("abc", exclude=["review"]).state == "pass"
        assert forge.ci_status("abc").state == "pending"

    @pytest.mark.parametrize(
        ("status", "conclusion", "expected"),
        [
            ("completed", "success", "pass"),
            ("completed", "neutral", "pass"),
            ("completed", "skipped", "pass"),
            ("completed", "failure", "fail"),
            ("completed", "timed_out", "fail"),
            ("completed", "cancelled", "fail"),
            ("queued", None, "pending"),
            ("in_progress", None, "pending"),
        ],
    )
    def test_ci_status_classifies_each_check_run(self, status: str, conclusion: str | None, expected: str) -> None:
        forge = GitHubForge(FakeRunner({"check-runs": json_lines(check_item("python", status, conclusion))}))

        assert forge.ci_status("abc").state == expected

    def test_ci_status_with_no_checks_is_none(self) -> None:
        assert GitHubForge(FakeRunner({"check-runs": ""})).ci_status("abc").state == "none"

    def test_ci_status_with_every_check_excluded_is_none(self) -> None:
        forge = GitHubForge(FakeRunner({"check-runs": json_lines(check_item("readiness"))}))

        assert forge.ci_status("abc", exclude=["readiness"]).state == "none"

    def test_current_user_requires_a_login(self) -> None:
        with pytest.raises(ForgeError, match="authenticated"):
            GitHubForge(FakeRunner({"api user": "\n"})).current_user()

    @pytest.mark.parametrize(
        ("responses", "call"),
        [
            ({"pr view": "not json"}, lambda forge: forge.pull_request(7)),
            ({"pr view": json.dumps({"number": 7})}, lambda forge: forge.pull_request(7)),
            ({"issues/7/comments": json.dumps({"id": 1})}, lambda forge: forge.find_comment(7, ["bot"])),
            ({"check-runs": json.dumps({"name": "python"})}, lambda forge: forge.ci_status("abc")),
        ],
    )
    def test_malformed_gh_output_becomes_a_forge_error(self, responses: dict[str, str], call: object) -> None:
        with pytest.raises(ForgeError, match="Unexpected gh output"):
            call(GitHubForge(FakeRunner(responses)))  # type: ignore[operator]

    def test_a_malformed_comment_write_reply_becomes_a_forge_error(self) -> None:
        runner = FakeRunner({"-X POST": "{}", "issues/7/comments --paginate": ""})

        with pytest.raises(ForgeError, match="Unexpected gh output"):
            GitHubForge(runner).upsert_comment(7, readiness_body(), ["bot"])


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


def ci(state: CiState, *checks: tuple[str, CiState]) -> CiStatus:
    return CiStatus(
        sha="abc123", state=state, checks=tuple(CheckRun(name, check_state) for name, check_state in checks)
    )


PYTHON_PASS = ci("pass", ("python", "pass"))
PYTHON_PENDING = ci("pending", ("python", "pending"))


class StubForge:
    """A forge with fixed answers that records what it is asked."""

    def __init__(
        self,
        previous: Comment | None = None,
        ci_sequence: Sequence[CiStatus] = (PYTHON_PASS,),
        user: str | None = "me",
        head_sha: str = "abc123",
    ) -> None:
        self.previous = previous
        self.ci_sequence = list(ci_sequence)
        self.user = user
        self.head_sha = head_sha
        self.ci_polls = 0
        self.pr_lookups = 0
        self.find_authors: Collection[str] = ()
        self.ci_excludes: list[Collection[str]] = []
        self.ci_shas: list[str] = []
        self.opened: list[tuple[str, str, str, str, bool]] = []
        self.ready: list[int] = []
        self.bodies: list[tuple[int, str]] = []
        self.upserted: list[str] = []
        self.upsert_authors: Collection[str] = ()

    def current_user(self) -> str:
        if self.user is None:
            raise ForgeError("no user")
        return self.user

    def pull_request(self, number: int | None) -> PullRequest:
        self.pr_lookups += 1
        return PullRequest(number or 7, "u", "develop", "feature/x", self.head_sha, False, "OPEN")

    def find_comment(self, number: int, authors: Collection[str]) -> Comment | None:
        self.find_authors = authors
        return self.previous

    def upsert_comment(self, number: int, body: str, authors: Collection[str]) -> tuple[Comment, bool]:
        require_marker(body)
        self.upserted.append(body)
        self.upsert_authors = authors
        return Comment(id=11, body=body, author="me"), self.previous is None

    def ci_status(self, sha: str, exclude: Collection[str] = ()) -> CiStatus:
        self.ci_excludes.append(exclude)
        self.ci_shas.append(sha)
        status = self.ci_sequence[min(self.ci_polls, len(self.ci_sequence) - 1)]
        self.ci_polls += 1
        return status

    def open_pull_request(self, base: str, head: str, title: str, body: str, draft: bool = True) -> PullRequest:
        self.opened.append((base, head, title, body, draft))
        return PullRequest(42, "https://example.test/pull/42", base, head, "claimed1", draft, "OPEN")

    def set_ready(self, number: int) -> None:
        self.ready.append(number)

    def set_pull_request_body(self, number: int, body: str) -> None:
        self.bodies.append((number, body))


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def sleep(self, seconds: float) -> None:
        self.now += seconds

    def __call__(self) -> float:
        return self.now


def wait(forge: StubForge, **kwargs: float) -> CiStatus:
    clock = FakeClock()
    return wait_for_ci(forge, "abc123", sleep=clock.sleep, clock=clock, **kwargs)


class TestWaitForCi:
    def test_no_checks_and_no_timeout_is_a_single_reading_of_none(self) -> None:
        forge = StubForge(ci_sequence=[ci("none")])

        assert wait(forge).state == "none"
        assert forge.ci_polls == 1

    def test_no_timeout_is_a_single_reading(self) -> None:
        forge = StubForge(ci_sequence=[PYTHON_PENDING, PYTHON_PASS])

        assert wait(forge).state == "pending"
        assert forge.ci_polls == 1

    def test_a_clean_reading_with_no_timeout_is_returned_without_polling_again(self) -> None:
        forge = StubForge()

        assert wait(forge).state == "pass"
        assert forge.ci_polls == 1

    def test_polls_until_checks_settle_and_the_same_checks_are_seen_twice(self) -> None:
        forge = StubForge(ci_sequence=[PYTHON_PENDING, PYTHON_PASS, PYTHON_PASS])

        status = wait(forge, timeout_seconds=100, interval_seconds=10)

        assert status.state == "pass"
        assert forge.ci_polls == 3

    def test_checks_that_appear_after_a_first_clean_reading_are_waited_for(self) -> None:
        early = ci("pass", ("changes", "pass"))
        starting = ci("pending", ("changes", "pass"), ("python", "pending"))
        done = ci("pass", ("changes", "pass"), ("python", "pass"))
        forge = StubForge(ci_sequence=[early, starting, done, done])

        status = wait(forge, timeout_seconds=100, interval_seconds=10)

        assert status.checks == done.checks
        assert forge.ci_polls == 4

    def test_none_counts_as_starting_until_the_grace_period_ends(self) -> None:
        forge = StubForge(ci_sequence=[ci("none")])

        status = wait(forge, timeout_seconds=500, interval_seconds=10, none_grace_seconds=30)

        assert status.state == "none"
        assert forge.ci_polls == 5

    def test_checks_that_appear_within_the_none_grace_are_used(self) -> None:
        forge = StubForge(ci_sequence=[ci("none"), ci("none"), PYTHON_PASS, PYTHON_PASS])

        status = wait(forge, timeout_seconds=500, interval_seconds=10, none_grace_seconds=60)

        assert status.state == "pass"

    def test_a_failure_is_returned_at_once(self) -> None:
        forge = StubForge(ci_sequence=[ci("fail", ("python", "fail"))])

        assert wait(forge, timeout_seconds=100, interval_seconds=10).state == "fail"
        assert forge.ci_polls == 1

    def test_gives_up_at_the_timeout_and_reports_pending(self) -> None:
        forge = StubForge(ci_sequence=[PYTHON_PENDING])

        status = wait(forge, timeout_seconds=25, interval_seconds=10)

        assert status.state == "pending"
        assert forge.ci_polls == 4

    def test_the_excluded_checks_reach_every_poll(self) -> None:
        forge = StubForge(ci_sequence=[PYTHON_PENDING, PYTHON_PASS, PYTHON_PASS])
        clock = FakeClock()

        wait_for_ci(forge, "abc123", ["readiness"], 100, 10, sleep=clock.sleep, clock=clock)

        assert forge.ci_excludes == [["readiness"]] * 3


class TestService:
    def test_resolve_authors_prefers_the_given_authors(self) -> None:
        assert resolve_authors(StubForge(), ["bot"]) == ("bot",)

    def test_resolve_authors_falls_back_to_the_authenticated_user(self) -> None:
        assert resolve_authors(StubForge(user="me"), []) == ("me",)

    def test_resolve_authors_fails_when_no_trusted_author_is_known(self) -> None:
        with pytest.raises(ForgeError, match="pass --author"):
            resolve_authors(StubForge(user=None), [])

    def test_review_context_bundles_pull_request_previous_comment_and_ci(self) -> None:
        forge = StubForge(previous=Comment(id=3, body=readiness_body(2, "old"), author="bot"))

        context = review_context(forge, 7, ["bot"])

        assert context["pull_request"]["diff_base_ref"] == "origin/develop"
        assert context["pull_request"]["head_sha"] == "abc123"
        assert context["previous_comment"]["body"].endswith("old")
        assert context["previous_pass"] == 2
        assert context["ci"]["state"] == "pass"
        assert forge.find_authors == ("bot",)

    def test_review_context_first_pass_has_no_previous_comment(self) -> None:
        context = review_context(StubForge(), None, [])

        assert context["previous_comment"] is None
        assert context["previous_pass"] is None
        assert context["pass_cap_reached"] is False

    def test_review_context_fails_when_the_head_moved(self) -> None:
        with pytest.raises(ForgeError, match="newer push"):
            review_context(StubForge(head_sha="new456"), 7, [], expected_sha="abc123")

    def test_review_context_accepts_the_expected_head(self) -> None:
        assert review_context(StubForge(), 7, [], expected_sha="abc123")["pull_request"]["head_sha"] == "abc123"

    def test_review_context_reports_the_pass_cap(self) -> None:
        forge = StubForge(previous=Comment(id=3, body=readiness_body(8), author="bot"))

        assert review_context(forge, 7, [], max_passes=8)["pass_cap_reached"] is True
        assert review_context(forge, 7, [], max_passes=9)["pass_cap_reached"] is False

    def test_review_context_fails_closed_when_the_previous_pass_cannot_be_read(self) -> None:
        forge = StubForge(previous=Comment(id=3, body=f"{READINESS_MARKER}\nno header", author="bot"))

        with pytest.raises(ForgeError, match="pass number"):
            review_context(forge, 7, [], max_passes=8)

    def test_review_context_without_a_cap_tolerates_an_unreadable_previous_pass(self) -> None:
        forge = StubForge(previous=Comment(id=3, body=f"{READINESS_MARKER}\nno header", author="bot"))

        assert review_context(forge, 7, [])["previous_pass"] is None

    def test_review_context_waits_for_ci_when_asked(self, monkeypatch: pytest.MonkeyPatch) -> None:
        forge = StubForge(ci_sequence=[PYTHON_PENDING, PYTHON_PASS, PYTHON_PASS])
        clock = FakeClock()
        monkeypatch.setattr(service_module.time, "sleep", clock.sleep)
        monkeypatch.setattr(service_module.time, "monotonic", clock)

        context = review_context(forge, 7, [], wait_seconds=100)

        assert context["ci"]["state"] == "pass"
        assert forge.ci_polls == 3

    def test_review_context_passes_the_excluded_checks_to_ci(self) -> None:
        forge = StubForge()

        review_context(forge, 7, [], exclude_checks=["readiness"])

        assert forge.ci_excludes == [["readiness"]]


class TestCli:
    def test_pr_info_prints_json(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert main(["pr-info", "--pr", "7"], StubForge()) == 0

        printed = json.loads(capsys.readouterr().out)
        assert printed["number"] == 7
        assert printed["diff_base_ref"] == "origin/develop"

    def test_comment_get_prints_null_when_absent(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert main(["comment-get", "--pr", "7"], StubForge()) == 0

        assert json.loads(capsys.readouterr().out) is None

    def test_comment_get_prints_an_existing_comment(self, capsys: pytest.CaptureFixture[str]) -> None:
        forge = StubForge(previous=Comment(id=3, body=readiness_body(), author="bot"))

        assert main(["comment-get", "--pr", "7", "--author", "bot"], forge) == 0

        assert json.loads(capsys.readouterr().out)["id"] == 3
        assert forge.find_authors == ("bot",)

    def test_a_given_pr_number_is_not_looked_up(self) -> None:
        forge = StubForge()

        main(["comment-get", "--pr", "7"], forge)

        assert forge.pr_lookups == 0

    def test_an_omitted_pr_number_is_looked_up(self) -> None:
        forge = StubForge()

        main(["comment-get"], forge)

        assert forge.pr_lookups == 1

    def test_comment_upsert_reads_the_body_file(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        body = tmp_path / "body.md"
        body.write_text(readiness_body(), encoding="utf-8")
        forge = StubForge()

        assert main(["comment-upsert", "--pr", "7", "--author", "bot", "--body-file", str(body)], forge) == 0

        assert json.loads(capsys.readouterr().out) == {"id": 11, "action": "created"}
        assert forge.upserted == [readiness_body()]
        assert forge.upsert_authors == ("bot",)

    def test_comment_upsert_reads_the_body_from_stdin(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr("sys.stdin", StringIO(readiness_body()))
        forge = StubForge()

        assert main(["comment-upsert", "--pr", "7", "--body-file", "-"], forge) == 0

        assert forge.upserted == [readiness_body()]
        assert json.loads(capsys.readouterr().out)["action"] == "created"

    def test_comment_upsert_refuses_a_body_without_the_marker(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        body = tmp_path / "body.md"
        body.write_text("not a readiness comment", encoding="utf-8")

        assert main(["comment-upsert", "--pr", "7", "--body-file", str(body)], StubForge()) == 1

        assert "must start with" in capsys.readouterr().err

    def test_review_context_passes_every_option_to_the_service(self, capsys: pytest.CaptureFixture[str]) -> None:
        forge = StubForge()
        argv = [
            "review-context",
            "--pr",
            "7",
            "--author",
            "bot",
            "--exclude",
            "readiness",
            "--wait",
            "0",
            "--expect-sha",
            "abc123",
            "--max-passes",
            "8",
        ]

        assert main(argv, forge) == 0

        printed = json.loads(capsys.readouterr().out)
        assert set(printed) == {"pull_request", "previous_comment", "previous_pass", "pass_cap_reached", "ci"}
        assert forge.find_authors == ("bot",)
        assert forge.ci_excludes == [["readiness"]]

    def test_review_context_reports_the_pass_cap_from_the_command_line(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        forge = StubForge(previous=Comment(id=3, body=readiness_body(8), author="bot"))

        assert main(["review-context", "--pr", "7", "--author", "bot", "--max-passes", "8"], forge) == 0

        assert json.loads(capsys.readouterr().out)["pass_cap_reached"] is True

    def test_review_context_stops_when_the_head_is_not_the_expected_commit(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(["review-context", "--pr", "7", "--expect-sha", "old000"], StubForge()) == 1

        assert "newer push" in capsys.readouterr().err

    def test_ci_status_accepts_an_explicit_sha(self, capsys: pytest.CaptureFixture[str]) -> None:
        forge = StubForge()

        assert main(["ci-status", "--sha", "deadbeef", "--exclude", "readiness"], forge) == 0

        assert forge.ci_shas == ["deadbeef"]
        assert forge.ci_excludes == [["readiness"]]
        assert json.loads(capsys.readouterr().out)["state"] == "pass"

    def test_ci_status_defaults_to_the_checked_out_commit(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        seen: list[str] = []

        class Recording(StubForge):
            def ci_status(self, sha: str, exclude: Collection[str] = ()) -> CiStatus:
                seen.append(sha)
                return super().ci_status(sha, exclude)

        monkeypatch.setattr(cli_module, "get_repo_root", lambda: Path("."))
        monkeypatch.setattr(cli_module, "git_output", lambda *_args: "feedface\n")

        assert main(["ci-status"], Recording()) == 0

        assert seen == ["feedface"]
        capsys.readouterr()

    def test_check_body_accepts_a_good_body(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        body = tmp_path / "body.md"
        body.write_text(readiness_body(2), encoding="utf-8")

        assert main(["check-body", "--body-file", str(body), "--previous-pass", "1"], StubForge()) == 0

        assert json.loads(capsys.readouterr().out) == {"ok": True}

    def test_check_body_reports_the_problems(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        body = tmp_path / "body.md"
        body.write_text(readiness_body(1), encoding="utf-8")

        assert main(["check-body", "--body-file", str(body), "--previous-pass", "4"], StubForge()) == 1

        assert "should say pass 5" in capsys.readouterr().err

    def test_check_body_rejects_the_value_of_a_forbidden_variable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("SPIKE_TEST_VALUE", "s3cr3t-value")
        body = tmp_path / "body.md"
        body.write_text(readiness_body(1, "leaked s3cr3t-value"), encoding="utf-8")

        assert main(["check-body", "--body-file", str(body), "--forbid-env", "SPIKE_TEST_VALUE"], StubForge()) == 1

        assert "forbidden" in capsys.readouterr().err

    def test_check_body_fails_when_a_forbidden_variable_is_unset(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.delenv("SPIKE_UNSET_VALUE", raising=False)
        body = tmp_path / "body.md"
        body.write_text(readiness_body(1), encoding="utf-8")

        assert main(["check-body", "--body-file", str(body), "--forbid-env", "SPIKE_UNSET_VALUE"], StubForge()) == 1

        assert "not set or empty" in capsys.readouterr().err

    def test_check_body_fails_when_no_body_was_written(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(["check-body", "--body-file", str(tmp_path / "missing.md")], StubForge()) == 1

        assert "did not write a comment body" in capsys.readouterr().err

    def test_a_forge_error_prints_to_stderr_and_exits_one(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert main(["comment-get", "--pr", "7"], StubForge(user=None)) == 1

        assert capsys.readouterr().err.startswith("forge: ")


class TestWriteOperations:
    def test_open_pull_request_creates_a_draft_from_a_body_on_stdin_and_reads_it_back(self) -> None:
        runner = FakeRunner(
            {
                "pr create": "https://github.com/o/r/pull/42\n",
                "pr view 42": json.dumps({**PR_JSON, "number": 42, "isDraft": True}),
            }
        )

        pr = GitHubForge(runner).open_pull_request("develop", "feature/x", "A title", "The body")

        create_args, stdin = runner.calls[0]
        assert create_args[:2] == ["pr", "create"]
        assert "--draft" in create_args and create_args[create_args.index("--base") + 1] == "develop"
        assert create_args[create_args.index("--body-file") + 1] == "-" and stdin == "The body"
        assert (pr.number, pr.is_draft) == (42, True)

    def test_a_non_draft_pull_request_omits_the_draft_flag(self) -> None:
        runner = FakeRunner({"pr create": "https://github.com/o/r/pull/42\n", "pr view 42": json.dumps(PR_JSON)})

        GitHubForge(runner).open_pull_request("develop", "feature/x", "t", "b", draft=False)

        assert "--draft" not in runner.calls[0][0]

    def test_an_unexpected_create_reply_is_a_forge_error(self) -> None:
        with pytest.raises(ForgeError, match="Unexpected gh output"):
            GitHubForge(FakeRunner({"pr create": "created\n"})).open_pull_request("develop", "f", "t", "b")

    def test_set_pull_request_body_sends_the_body_on_stdin(self) -> None:
        runner = FakeRunner({"pr edit 7": ""})

        GitHubForge(runner).set_pull_request_body(7, "New description")

        assert runner.calls[0] == (["pr", "edit", "7", "--body-file", "-"], "New description")

    def test_set_ready_marks_the_pull_request_ready(self) -> None:
        runner = FakeRunner({"pr ready 7": ""})

        GitHubForge(runner).set_ready(7)

        assert runner.calls[0][0] == ["pr", "ready", "7"]


class TestPublishProblems:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("ping @someone", "a mention"),
            ("see https://example.test", "a URL"),
            ("see www.example.test", "a URL"),
            ("a <b>tag</b>", "HTML"),
            ("![alt](x.png)", "an image or link"),
            ("at /home/someone/project", "a local path"),
            (r"at C:\work\x", "a local path"),
            ("notes in local/strategies", "private local folder"),
            ("account DU1234567 holds", "broker account id"),
        ],
    )
    def test_each_unsafe_shape_is_refused(self, text: str, expected: str) -> None:
        from scripts.forge.readiness import publish_problems

        assert any(expected in problem for problem in publish_problems(text))

    @pytest.mark.parametrize(
        "text",
        [
            "Added `@pytest.mark.parametrize` tests in src/common/tickers.py.",
            "Fixed the wait in scripts/forge/service.py (see #301).",
            "Code: ```python\nx = '@y'  # <b>\n```",
        ],
    )
    def test_ordinary_summaries_and_code_are_allowed(self, text: str) -> None:
        from scripts.forge.readiness import publish_problems

        assert publish_problems(text) == []


class FakeSandboxes:
    """Stands in for the sandbox factory: records the commit each sandbox was cut from and when it closed."""

    def __init__(self, base: Path) -> None:
        self.base = base
        self.refs: list[str] = []
        self.installs: list[bool] = []
        self.closed = 0
        self.dirty: list[str] = []

    def __call__(self, ref: str, install: bool = True):  # type: ignore[no-untyped-def]
        from contextlib import contextmanager
        from dataclasses import dataclass

        from scripts.forge.sandbox import Sandbox

        dirty = self.dirty

        @dataclass(frozen=True)
        class Box(Sandbox):
            def uncommitted(self) -> list[str]:
                return list(dirty)

        @contextmanager
        def opened():  # type: ignore[no-untyped-def]
            self.refs.append(ref)
            self.installs.append(install)
            try:
                yield Box(self.base / ("box" if len(self.refs) == 1 else f"box{len(self.refs)}"))
            finally:
                self.closed += 1

        return opened()


class TestPublicTextShapes:
    @pytest.mark.parametrize(
        "text",
        [
            "see /home/alice/project/file.py",
            "see ~/project/file.py",
            "see C:/Users/alice/project",
            "account DU1234567 needs review",
        ],
    )
    def test_more_paths_and_account_ids_are_refused_in_the_readiness_comment(self, text: str) -> None:
        assert body_problems(readiness_body(1, text), None) != []

    def test_prose_with_a_home_word_or_a_relative_path_is_fine(self) -> None:
        assert body_problems(readiness_body(1, "the src/home/page.py file and home/ folder"), None) == []

    def test_too_many_added_status_lines_in_one_round_are_refused(self) -> None:
        old = "- [ ] **1. A.** text\n"
        new = old + "\n".join(f"  *Left: reason number {n}*" for n in range(13)) + "\n"

        assert any("status lines" in p for p in fixer_edit_problems(old, new))

    def test_exactly_twelve_added_status_lines_are_accepted(self) -> None:
        old = "- [ ] **1. A.** text" + chr(10)
        new = old + chr(10).join(f"  *Left: reason number {n}*" for n in range(12)) + chr(10)

        assert fixer_edit_problems(old, new) == []


class TestPathFilters:
    def test_the_publish_filter_refuses_every_form_the_comment_filter_refuses(self) -> None:
        from scripts.forge.readiness import leak_problems, publish_problems

        for text in ("see ~/project/file.py", "see C:/Users/alice/project", "see /home/alice/project/file.py"):
            assert leak_problems(text) and publish_problems(text)

    def test_a_bare_home_name_passes_the_comment_filter_but_not_the_publish_filter(self) -> None:
        from scripts.forge.readiness import leak_problems, publish_problems

        assert leak_problems("the user lives in /home/alice") == []
        assert publish_problems("the user lives in /home/alice") != []

    def test_the_windows_backslash_profile_form_is_refused_in_both(self) -> None:
        from scripts.forge.readiness import leak_problems, publish_problems

        text = "see C:" + chr(92) + "Users" + chr(92) + "alice" + chr(92) + "file"
        assert leak_problems(text) and publish_problems(text)

    def test_an_account_id_shape_inside_a_code_block_is_still_refused(self) -> None:
        from scripts.forge.readiness import leak_problems

        assert leak_problems("```" + chr(10) + "DU1234567" + chr(10) + "```") != []


BACKSLASH = chr(92)


class TestWiderLeakShapes:
    @pytest.mark.parametrize(
        "text",
        [
            f"see c:{BACKSLASH}users{BACKSLASH}alice{BACKSLASH}x",
            "see C:/USERS/alice/x",
            f"see C:{BACKSLASH}{BACKSLASH}Users{BACKSLASH}{BACKSLASH}alice{BACKSLASH}{BACKSLASH}x",
            "see C://Users//alice",
            f"see ~{BACKSLASH}project",
        ],
        ids=["lowercase", "uppercase-forward", "json-escaped", "doubled-forward", "tilde-backslash"],
    )
    def test_each_form_of_a_user_profile_path_is_refused_in_a_comment(self, text: str) -> None:
        from scripts.forge.readiness import leak_problems

        assert any("local path" in problem for problem in leak_problems(text))

    def test_a_placeholder_is_still_accepted_when_the_separators_are_doubled_or_the_case_differs(self) -> None:
        from scripts.forge.readiness import leak_problems

        for text in (
            f"see C:{BACKSLASH}{BACKSLASH}Users{BACKSLASH}{BACKSLASH}<user>{BACKSLASH}{BACKSLASH}x",
            f"see c:{BACKSLASH}users{BACKSLASH}<username>{BACKSLASH}x",
        ):
            assert leak_problems(text) == []

    @pytest.mark.parametrize(
        "pieces",
        [
            ("github_pat_", "11ABCDEFG0", "A1b2C3d4" * 6),
            ("AK", "IA", "ABCDEFGHIJKLMNOP"),
            ("xo", "xb-", "1234567890-", "1234567890-", "AbCdEfGh"),
            ("ey", "Jhbgcioijiuzi1nij9", ".", "ey", "JzdWIiOiIxMjM0NTY3ODkwIn0", ".", "abcDEF123_-abcDEF123"),
            ("-----BEGIN ", "RSA ", "PRIVATE KEY-----"),
        ],
        ids=["fine-grained-pat", "aws-access-key", "slack-token", "jwt", "private-key-header"],
    )
    def test_more_credential_shapes_are_refused(self, pieces: tuple[str, ...]) -> None:
        from scripts.forge.readiness import leak_problems

        assert any("credential" in problem for problem in leak_problems("see " + "".join(pieces) + " here"))

    @pytest.mark.parametrize("text", ["acct_DU1234567", "DU1234567_paper", "file-DU1234567.csv", "DU1234567abc"])
    def test_an_account_id_next_to_an_underscore_or_letters_is_refused(self, text: str) -> None:
        from scripts.forge.readiness import leak_problems

        assert any("account id" in problem for problem in leak_problems(text))

    @pytest.mark.parametrize(
        "text", ["abcDU1234567", "DU12345678901", "DU12345", "see commit 73bb23aa and ticket 1234567"]
    )
    def test_ordinary_text_next_to_digits_is_not_mistaken_for_an_account_id(self, text: str) -> None:
        from scripts.forge.readiness import leak_problems

        assert not any("account id" in problem for problem in leak_problems(text))


ESC = chr(27)
BEL = chr(7)


class TestContainsAmbientSecret:
    def test_the_token_in_any_covered_form_is_found_when_it_is_in_the_environment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from scripts.forge.readiness import contains_ambient_secret

        value = "".join(["sk", "-ant-", "oat01-", "Ab3_x-Qz9" * 8])
        monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", value)

        assert contains_ambient_secret("x " + value + " y")
        assert contains_ambient_secret(value[::-1])
        assert contains_ambient_secret(value.encode().hex())

    def test_nothing_is_found_without_a_long_enough_value_in_the_environment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from scripts.forge.readiness import contains_ambient_secret

        monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
        assert not contains_ambient_secret("anything at all")
        monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "short")
        assert not contains_ambient_secret("a short word and the short value")


class TestPrintable:
    def test_control_sequences_are_shown_as_escapes_not_acted_on(self) -> None:
        from scripts.forge.base import printable

        text = f"ok {ESC}[31mred{ESC}[0m {ESC}]52;c;ZXZpbA=={BEL} end"

        shown = printable(text)

        assert ESC not in shown and BEL not in shown
        assert "\\u001b[31mred" in shown and "\\u0007" in shown

    def test_bidirectional_overrides_and_zero_width_characters_are_escaped(self) -> None:
        from scripts.forge.base import printable

        shown = printable("a\u202eb\u200bc\u0085d")

        assert shown == "a\\u202eb\\u200bc\\u0085d"

    def test_newlines_tabs_and_ordinary_text_pass_through(self) -> None:
        from scripts.forge.base import printable

        text = "line one\n\tindented \u00e9\u4e2d\U0001f600 and punctuation: (a) [b] {c} <d>"

        assert printable(text) == text

    def test_an_astral_control_like_character_uses_the_long_escape(self) -> None:
        from scripts.forge.base import printable

        assert printable("x\U000e0041y") == "x\\U000e0041y"

    def test_the_cli_prints_a_failure_message_without_raw_control_characters(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        def failing(args: object, forge: object) -> None:
            raise ForgeError(f"The agent failed: {ESC}[2J{ESC}]0;owned{BEL}")

        monkeypatch.setitem(cli_module.COMMANDS, "pr-info", failing)

        assert main(["pr-info", "--pr", "1"], StubForge()) == 1

        err = capsys.readouterr().err
        assert ESC not in err and BEL not in err and "owned" in err


class TestPlaceholderThenParent:
    @pytest.mark.parametrize(
        "text",
        [
            "see /Users/<user>/../alice/x",
            f"see C:{BACKSLASH}Users{BACKSLASH}<user>{BACKSLASH}..{BACKSLASH}alice{BACKSLASH}x",
            "see /home/<name>/../alice/project/x",
            f"see C:{BACKSLASH}{BACKSLASH}Users{BACKSLASH}{BACKSLASH}<user>{BACKSLASH}{BACKSLASH}..{BACKSLASH}{BACKSLASH}a",
        ],
        ids=["mac", "windows", "linux", "json-escaped"],
    )
    def test_a_placeholder_followed_by_a_parent_reference_is_refused(self, text: str) -> None:
        from scripts.forge.readiness import leak_problems

        assert any("local path" in problem for problem in leak_problems(text))

    def test_a_placeholder_followed_by_an_ordinary_name_is_still_accepted(self) -> None:
        from scripts.forge.readiness import leak_problems

        for text in ("see /Users/<user>/..hidden/x", "see /Users/<user>/docs/x", "see C:/Users/<name>/.config/x"):
            assert leak_problems(text) == []


def _long_value() -> str:
    return "".join(["sk", "-ant-", "oat01-", "Ab3_x-Qz9" * 8])


class TestForbiddenValueDisguises:
    @pytest.mark.parametrize(
        "make",
        [
            lambda v: v,
            lambda v: v[::-1],
            lambda v: v.encode().hex(),
            lambda v: v.encode().hex().upper(),
            lambda v: __import__("base64").b64encode(v.encode()).decode(),
            lambda v: __import__("base64").urlsafe_b64encode(v.encode()).decode().rstrip("="),
            lambda v: " ".join(v[i : i + 12] for i in range(0, len(v), 12)),
            lambda v: chr(10).join(v[i : i + 9] for i in range(0, len(v), 9)),
        ],
        ids=["plain", "reversed", "hex", "hex-upper", "base64", "urlsafe-unpadded", "spaced", "line-wrapped"],
    )
    def test_a_long_forbidden_value_is_refused_in_each_disguise(self, make: object) -> None:
        from scripts.forge.readiness import leak_problems

        value = _long_value()
        text = "Summary: all done. " + make(value) + " Nothing else."  # type: ignore[operator]

        assert any("forbidden" in problem for problem in leak_problems(text, [value]))

    def test_the_claude_token_in_the_environment_is_refused_without_being_listed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from scripts.forge.readiness import leak_problems, publish_problems

        value = _long_value()
        monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", value)
        hexed = "Summary: " + value.encode().hex()

        assert any("forbidden" in problem for problem in leak_problems(hexed))
        assert any("forbidden" in problem for problem in publish_problems(hexed))

    def test_an_unset_or_short_environment_value_blocks_nothing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from scripts.forge.readiness import leak_problems

        monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
        assert leak_problems("Summary: added two tests.") == []
        monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "abc")
        assert leak_problems("abc is a short word and the value is too short to check") == []

    def test_a_short_forbidden_value_is_matched_as_written_only(self) -> None:
        from scripts.forge.readiness import leak_problems

        assert leak_problems("value s3cr3t here", ["s3cr3t"]) != []
        assert leak_problems("hex " + b"s3cr3t".hex(), ["s3cr3t"]) == []

    def test_ordinary_prose_and_unrelated_encodings_pass(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from scripts.forge.readiness import leak_problems

        monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", _long_value())
        text = "Added tests. See commit 73bb23aa and " + "ab" * 40

        assert leak_problems(text) == []


def test_a_url_inside_code_is_not_mistaken_for_a_drive_letter_path() -> None:
    from scripts.forge.readiness import publish_problems

    assert publish_problems("the endpoint `https://example.test/x` is stable") == []
    assert publish_problems("see C:/Users/alice/x") != []


class TestPlaceholderPaths:
    BACKSLASH = chr(92)

    def test_an_angle_bracket_placeholder_in_place_of_the_user_name_is_allowed(self) -> None:
        from scripts.forge.readiness import leak_problems, publish_problems

        for text in (
            "the pattern matches /Users/<user>/x",
            "and /home/<name>/project/file.py",
            "and C:/Users/<user>/x",
            "and C:" + self.BACKSLASH + "Users" + self.BACKSLASH + "<user>" + self.BACKSLASH + "x",
        ):
            assert leak_problems(text) == [], text
            assert publish_problems("`" + text + "`") == [], text

    def test_a_real_user_name_is_still_refused_even_next_to_a_placeholder(self) -> None:
        from scripts.forge.readiness import leak_problems

        for text in (
            "/Users/<user>/x and /Users/alice/x",
            "/home/<name>/a and /home/alice/a",
            "C:/Users/<user>/x and C:/Users/alice/x",
            "/Users/alice<user>/x",
        ):
            assert leak_problems(text) != [], text

    def test_the_runner_path_and_the_tilde_form_are_not_affected(self) -> None:
        from scripts.forge.readiness import leak_problems

        assert leak_problems("/home/runner/work/x") != [] and leak_problems("see ~/project/file") != []


class TestOnlyTheListedPlaceholdersAreExempt:
    @pytest.mark.parametrize("name", ["user", "username", "name", "segment"])
    def test_each_listed_placeholder_is_allowed(self, name: str) -> None:
        from scripts.forge.readiness import leak_problems

        for text in (f"/Users/<{name}>/x", f"/home/<{name}>/x", f"C:/Users/<{name}>/x", f"see /Users/<{name}>"):
            assert leak_problems(text) == [], text

    @pytest.mark.parametrize("name", ["jdoe", "alice", "user2", "USER", ""])
    def test_any_other_bracketed_name_is_refused(self, name: str) -> None:
        from scripts.forge.readiness import leak_problems, publish_problems

        for text in (f"/Users/<{name}>/x", f"/home/<{name}>/x", f"C:/Users/<{name}>/x"):
            assert leak_problems(text) != [], text
            assert publish_problems("`" + text + "`") != [], text

    def test_a_placeholder_followed_by_more_name_is_refused(self) -> None:
        from scripts.forge.readiness import leak_problems

        assert leak_problems("/Users/<user>alice/x") != [] and leak_problems("/Users/<user>x") != []


@pytest.mark.parametrize("after", [")", ".", ",", "x", ">"])
def test_a_listed_placeholder_must_end_at_a_separator_so_trailing_punctuation_is_refused(after: str) -> None:
    from scripts.forge.readiness import leak_problems

    assert leak_problems(f"the path /Users/<user>{after}") != []
    assert leak_problems("the path /Users/<user>/ and /Users/<user>") == []
