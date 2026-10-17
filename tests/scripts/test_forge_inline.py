import json
from collections.abc import Collection, Sequence

import pytest

from scripts.forge import cli as cli_module
from scripts.forge.base import (
    FINDING_MARKER,
    READINESS_MARKER,
    ForgeError,
    InlineComment,
    PullRequest,
    finding_marker_number,
    require_finding_marker,
)
from scripts.forge.findings import parse_findings
from scripts.forge.github import GitHubForge, new_side_lines
from scripts.forge.inline import anchor_of, render, sync_inline_comments


def readiness(findings: str, closed: str = "", pass_no: int = 1) -> str:
    return (
        f"{READINESS_MARKER}\n## PR readiness: NOT READY\n\nReviewed `abc` · 2026-10-17 · pass {pass_no}\n\n"
        f"#### 🔴 Blockers\nNone.\n\n#### 🟠 Concerns\n{findings}\n\n"
        f"<details>\n<summary>✓ Closed</summary>\n\n#### Closed\n{closed}\n</details>\n"
    )


CONCERN = (
    "- [ ] **1. A broker error is swallowed.** `src/x.py:10`: the guard error is caught. → Re-raise it. [Break it]\n"
)
DIFF = {"src/x.py": frozenset({9, 10, 11}), "src/y.py": frozenset({3})}


class InlineStub:
    """An in-memory forge that keeps the review comments the sync writes."""

    def __init__(self, diff: dict[str, frozenset[int]] | None = None, comments: list[InlineComment] | None = None):
        self.diff = DIFF if diff is None else diff
        self.comments = comments or []
        self.created: list[tuple[str, int, str]] = []
        self.cannot_resolve = False
        self.edited: dict[int, str] = {}
        self.resolved: list[str] = []

    def diff_lines(self, number: int) -> dict[str, frozenset[int]]:
        return self.diff

    def inline_comments(self, number: int, authors: Collection[str]) -> list[InlineComment]:
        return [c for c in self.comments if c.author in authors]

    def create_inline_comment(self, number: int, head_sha: str, path: str, line: int, body: str) -> int:
        require_finding_marker(body)
        self.created.append((path, line, body))
        return 100 + len(self.created)

    def edit_inline_comment(self, comment_id: int, body: str) -> None:
        self.edited[comment_id] = body

    def resolve_thread(self, thread_id: str) -> None:
        if self.cannot_resolve:
            raise ForgeError("Resource not accessible by integration")
        self.resolved.append(thread_id)


def existing(number: int = 1, body: str | None = None, **overrides: object) -> InlineComment:
    fields = {
        "id": 7,
        "thread_id": "T7",
        "body": body or f"{FINDING_MARKER.format(number=number)}\n{CONCERN[6:].rstrip()}",
        "author": "bot",
        "path": "src/x.py",
        "line": 10,
        "resolved": False,
        "outdated": False,
    }
    fields.update(overrides)
    return InlineComment(**fields)  # type: ignore[arg-type]


def run_sync(stub: InlineStub, body: str) -> dict[str, int]:
    return sync_inline_comments(stub, 3, "sha1", body, ["bot"])  # type: ignore[arg-type]


class TestParsing:
    def test_a_finding_keeps_its_text_with_the_checkbox_removed(self) -> None:
        body = readiness(CONCERN + "  *Decision: Approved.*\n")

        finding = next(f for f in parse_findings(body) if f.number == 1)

        assert finding.text.splitlines()[0].startswith("**1. A broker error is swallowed.**")
        assert finding.text.splitlines()[1] == "*Decision: Approved.*"

    @pytest.mark.parametrize(
        ("line", "expected"),
        [
            ("**1. T.** `src/x.py:10`: problem.", ("src/x.py", 10)),
            ("**1. T.** `src/x.py:129-131`: problem.", ("src/x.py", 129)),
            ("**1. T.** A design problem with no line.", None),
        ],
    )
    def test_the_anchor_is_the_first_path_and_line(self, line: str, expected: tuple[str, int] | None) -> None:
        body = readiness(f"- [ ] {line}\n")

        assert anchor_of(next(f for f in parse_findings(body) if f.number == 1)) == expected

    def test_a_patch_gives_added_and_context_lines_on_the_new_side(self) -> None:
        patch = "@@ -1,3 +1,4 @@\n a\n-b\n+c\n+d\n e\n@@ -20,2 +21,2 @@\n x\n+y\n\\ No newline at end of file"

        assert new_side_lines(patch) == frozenset({1, 2, 3, 4, 21, 22})

    def test_markers(self) -> None:
        assert finding_marker_number(f"{FINDING_MARKER.format(number=12)}\ntext") == 12
        assert finding_marker_number("text") is None
        with pytest.raises(ForgeError, match="must start with"):
            require_finding_marker("not a finding")


class TestSync:
    def test_a_new_concern_on_a_changed_line_gets_one_comment(self) -> None:
        stub = InlineStub()

        counts = run_sync(stub, readiness(CONCERN))

        assert counts["created"] == 1
        [(path, line, body)] = stub.created
        assert (path, line) == ("src/x.py", 10)
        assert body.startswith(FINDING_MARKER.format(number=1))
        assert "A broker error is swallowed." in body

    def test_a_second_pass_with_the_same_finding_changes_nothing(self) -> None:
        stub = InlineStub(comments=[existing()])

        counts = run_sync(stub, readiness(CONCERN, pass_no=2))

        assert counts == {"created": 0, "edited": 0, "resolved": 0, "skipped": 0, "unresolved": 0}
        assert stub.created == [] and stub.edited == {} and stub.resolved == []

    def test_changed_text_edits_the_comment_in_place(self) -> None:
        stub = InlineStub(comments=[existing()])
        reworded = CONCERN.replace("Re-raise it.", "Re-raise it and add a test.")

        counts = run_sync(stub, readiness(reworded, pass_no=2))

        assert counts["edited"] == 1 and stub.created == []
        assert "add a test" in stub.edited[7]

    def test_a_finding_that_closes_is_marked_fixed_and_its_thread_resolved(self) -> None:
        stub = InlineStub(comments=[existing()])
        closed = "- [x] **1. A broker error is swallowed.** Fixed in `abc1234`: it re-raises now.\n"

        counts = run_sync(stub, readiness("None.", closed=closed, pass_no=2))

        assert counts["resolved"] == 1
        assert stub.resolved == ["T7"]
        assert "✓ **1. A broker error is swallowed.** Fixed in `abc1234`" in stub.edited[7]

    def test_a_finding_that_leaves_the_comment_is_resolved(self) -> None:
        stub = InlineStub(comments=[existing()])

        run_sync(stub, readiness("None.", pass_no=2))

        assert stub.resolved == ["T7"]
        assert "No longer in the readiness comment" in stub.edited[7]

    def test_a_line_outside_the_diff_is_skipped_and_stays_in_the_summary_only(self) -> None:
        stub = InlineStub()
        elsewhere = CONCERN.replace("src/x.py:10", "src/x.py:500")

        counts = run_sync(stub, readiness(elsewhere))

        assert counts["skipped"] == 1 and stub.created == []

    def test_a_file_outside_the_diff_is_skipped(self) -> None:
        stub = InlineStub()

        counts = run_sync(stub, readiness(CONCERN.replace("src/x.py", "docs/z.md")))

        assert counts["skipped"] == 1

    def test_a_finding_about_no_line_gets_no_comment(self) -> None:
        stub = InlineStub()

        counts = run_sync(
            stub, readiness("- [ ] **1. A design problem.** The layering is wrong. → Move it. [Architecture]\n")
        )

        assert counts == {"created": 0, "edited": 0, "resolved": 0, "skipped": 0, "unresolved": 0}

    def test_a_moved_finding_resolves_the_old_comment_and_posts_a_new_one(self) -> None:
        stub = InlineStub(comments=[existing()])

        counts = run_sync(stub, readiness(CONCERN.replace("src/x.py:10", "src/x.py:11"), pass_no=2))

        assert counts["created"] == 1 and counts["resolved"] == 1
        assert stub.created[0][:2] == ("src/x.py", 11)
        assert "Moved: the finding now sits on src/x.py:11" in stub.edited[7]

    def test_an_outdated_comment_is_replaced_even_on_the_same_line(self) -> None:
        stub = InlineStub(comments=[existing(outdated=True, line=None)])

        counts = run_sync(stub, readiness(CONCERN, pass_no=2))

        assert counts["created"] == 1 and stub.resolved == ["T7"]

    def test_notes_never_get_a_comment(self) -> None:
        stub = InlineStub()
        body = (
            f"{READINESS_MARKER}\n## PR readiness: READY\n\nReviewed `abc` · 2026-10-17 · pass 1\n\n"
            "#### 🟡 Notes (1)\n- [ ] **2. A name.** `src/x.py:10`: public. → Make it private. [Simplifier]\n"
        )

        assert run_sync(stub, body)["created"] == 0

    def test_a_finding_lowered_to_a_note_has_its_comment_resolved(self) -> None:
        stub = InlineStub(comments=[existing()])
        body = (
            f"{READINESS_MARKER}\n## PR readiness: READY\n\nReviewed `abc` · 2026-10-17 · pass 2\n\n"
            "#### 🟡 Notes (1)\n- [ ] **1. A broker error is swallowed.** `src/x.py:10`: x. → y. [Break it]\n"
        )

        run_sync(stub, body)

        assert stub.resolved == ["T7"]
        assert "Lowered to a note" in stub.edited[7]

    def test_comments_by_other_authors_are_left_alone(self) -> None:
        stub = InlineStub(comments=[existing(author="stranger")])

        counts = run_sync(stub, readiness(CONCERN))

        assert counts["created"] == 1 and stub.resolved == []

    def test_render_starts_with_the_marker(self) -> None:
        finding = next(f for f in parse_findings(readiness(CONCERN)) if f.number == 1)

        assert render(finding).startswith(FINDING_MARKER.format(number=1) + "\n**1. ")


class FakeRunner:
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


class TestGitHubInline:
    def test_diff_lines_reads_each_file_patch(self) -> None:
        item = {"filename": "src/x.py", "patch": "@@ -1,1 +5,2 @@\n a\n+b"}
        runner = FakeRunner({"pulls/3/files": json.dumps(item)})

        assert GitHubForge(runner).diff_lines(3) == {"src/x.py": frozenset({5, 6})}

    def test_inline_comments_keeps_only_finding_comments_by_the_named_authors(self) -> None:
        def node(thread: str, login: str, body: str, resolved: bool = False) -> dict[str, object]:
            comment = {"databaseId": 5, "body": body, "path": "src/x.py", "line": 10, "author": {"login": login}}
            return {"thread": thread, "resolved": resolved, "outdated": False, "comment": comment}

        output = "\n".join(
            json.dumps(item)
            for item in (
                node("T1", "bot", f"{FINDING_MARKER.format(number=1)}\ntext"),
                node("T2", "bot", "a plain comment"),
                node("T3", "stranger", f"{FINDING_MARKER.format(number=2)}\ntext"),
            )
        )
        runner = FakeRunner({"repo view": "o/r\n", "graphql": output})

        [comment] = GitHubForge(runner).inline_comments(3, ["bot"])

        assert (comment.thread_id, comment.finding_number, comment.line) == ("T1", 1, 10)

    def test_create_posts_a_right_side_review_comment(self) -> None:
        runner = FakeRunner({"-X POST": json.dumps({"id": 55})})
        body = f"{FINDING_MARKER.format(number=1)}\ntext"

        comment_id = GitHubForge(runner).create_inline_comment(3, "sha1", "src/x.py", 10, body)

        assert comment_id == 55
        args, stdin = runner.calls[-1]
        assert args[:4] == ["api", "-X", "POST", "repos/{owner}/{repo}/pulls/3/comments"]
        assert json.loads(stdin or "") == {
            "body": body,
            "commit_id": "sha1",
            "path": "src/x.py",
            "line": 10,
            "side": "RIGHT",
        }

    def test_an_inline_write_without_a_finding_marker_is_refused_before_calling_gh(self) -> None:
        runner = FakeRunner({})
        forge = GitHubForge(runner)

        with pytest.raises(ForgeError, match="must start with"):
            forge.create_inline_comment(3, "sha1", "src/x.py", 10, "an ordinary comment")
        with pytest.raises(ForgeError, match="must start with"):
            forge.edit_inline_comment(5, "an ordinary comment")

        assert runner.calls == []

    def test_edit_and_resolve_use_the_right_endpoints(self) -> None:
        runner = FakeRunner({"-X PATCH": "{}", "graphql": "{}"})
        forge = GitHubForge(runner)

        forge.edit_inline_comment(5, f"{FINDING_MARKER.format(number=1)}\nnew")
        forge.resolve_thread("T9")

        assert runner.calls[0][0][:4] == ["api", "-X", "PATCH", "repos/{owner}/{repo}/pulls/comments/5"]
        assert "threadId=T9" in runner.calls[1][0]


class TestCli:
    def test_inline_sync_reads_the_body_and_prints_the_counts(self, tmp_path, capsys) -> None:
        class CliStub(InlineStub):
            def current_user(self) -> str:
                return "bot"

            def pull_request(self, number: int | None) -> PullRequest:
                return PullRequest(3, "u", "develop", "feature", "headsha", False, "OPEN")

        stub = CliStub()
        body_file = tmp_path / "body.md"
        body_file.write_text(readiness(CONCERN), encoding="utf-8")

        code = cli_module.main(
            ["inline-sync", "--pr", "3", "--author", "bot", "--body-file", str(body_file)],
            forge=stub,  # type: ignore[arg-type]
        )

        assert code == 0
        assert json.loads(capsys.readouterr().out)["created"] == 1
        assert stub.created[0][:2] == ("src/x.py", 10)

    def test_a_forge_without_inline_support_is_refused(self, tmp_path, capsys) -> None:
        class Plain:
            def current_user(self) -> str:
                return "bot"

            def pull_request(self, number: int | None) -> PullRequest:
                return PullRequest(3, "u", "develop", "feature", "headsha", False, "OPEN")

        body_file = tmp_path / "body.md"
        body_file.write_text(readiness(CONCERN), encoding="utf-8")

        code = cli_module.main(
            ["inline-sync", "--pr", "3", "--author", "bot", "--body-file", str(body_file)],
            forge=Plain(),  # type: ignore[arg-type]
        )

        assert code == 1
        assert "cannot post inline review comments" in capsys.readouterr().err


class TestSyncMore:
    def test_a_finding_that_moves_off_the_diff_has_its_comment_edited_and_resolved(self) -> None:
        stub = InlineStub(comments=[existing()])
        off_diff = CONCERN.replace("src/x.py:10", "src/x.py:500")

        counts = run_sync(stub, readiness(off_diff, pass_no=2))

        assert counts == {"created": 0, "edited": 0, "resolved": 1, "skipped": 1, "unresolved": 0}
        assert "no longer on a changed line" in stub.edited[7]
        assert stub.resolved == ["T7"]

    def test_two_open_comments_for_one_finding_keep_exactly_one(self) -> None:
        stub = InlineStub(comments=[existing(), existing(id=8, thread_id="T8")])

        counts = run_sync(stub, readiness(CONCERN, pass_no=2))

        assert counts["resolved"] == 1 and counts["created"] == 0
        assert stub.resolved == ["T8"]
        assert "Duplicate of another comment" in stub.edited[8]

    def test_a_thread_a_person_resolved_is_not_reposted(self) -> None:
        stub = InlineStub(comments=[existing(resolved=True)])

        counts = run_sync(stub, readiness(CONCERN, pass_no=2))

        assert counts["created"] == 0 and stub.created == []

    def test_an_outdated_comment_is_called_replaced_not_moved(self) -> None:
        stub = InlineStub(comments=[existing(outdated=True)])

        run_sync(stub, readiness(CONCERN, pass_no=2))

        assert "Replaced: the code under this comment changed" in stub.edited[7]

    def test_an_open_finding_under_an_unknown_heading_is_not_ticked(self) -> None:
        stub = InlineStub(comments=[existing()])
        body = (
            f"{READINESS_MARKER}\n## PR readiness: READY\n\nReviewed `abc` · 2026-10-17 · pass 2\n\n"
            "#### Something else\n- [ ] **1. A broker error is swallowed.** `src/x.py:10`: x. → y. [Break it]\n"
        )

        run_sync(stub, body)

        assert stub.edited[7].endswith("See the readiness comment.")
        assert "✓" not in stub.edited[7]


class TestGitHubInlineArguments:
    def test_the_threads_query_is_paginated_and_asks_for_the_fields_the_code_reads(self) -> None:
        runner = FakeRunner({"repo view": "o/r\n", "graphql": ""})

        GitHubForge(runner).inline_comments(3, ["github-actions[bot]"])

        args, _ = runner.calls[-1]
        assert args[:3] == ["api", "graphql", "--paginate"]
        query = next(arg for arg in args if arg.startswith("query="))
        for field in ("reviewThreads", "isResolved", "isOutdated", "databaseId", "endCursor", "author { login }"):
            assert field in query
        assert "owner=o" in args and "name=r" in args and "number=3" in args

    def test_the_files_call_is_paginated(self) -> None:
        runner = FakeRunner({"pulls/3/files": ""})

        GitHubForge(runner).diff_lines(3)

        assert "--paginate" in runner.calls[-1][0]

    def test_a_graphql_bot_login_matches_the_rest_spelling_of_the_author(self) -> None:
        def thread(login: str | None) -> str:
            author = None if login is None else {"login": login}
            comment = {"databaseId": 5, "body": f"{FINDING_MARKER.format(number=1)}\nx", "path": "a", "line": 1}
            return json.dumps(
                {"thread": "T", "resolved": False, "outdated": False, "comment": {**comment, "author": author}}
            )

        runner = FakeRunner({"repo view": "o/r\n", "graphql": thread("github-actions") + "\n" + thread(None)})

        comments = GitHubForge(runner).inline_comments(3, ["github-actions[bot]"])

        assert [c.author for c in comments] == ["github-actions"]


class TestResolveRefused:
    def test_a_thread_that_cannot_be_resolved_stays_open_and_the_sync_goes_on(self) -> None:
        stub = InlineStub(comments=[existing()])
        stub.cannot_resolve = True
        other = "- [ ] **2. Another.** `src/y.py:3`: x. → y. [Operator]\n"
        closed = "- [x] **1. A broker error is swallowed.** Fixed in `abc1234`: ok. [Break it]\n"

        counts = run_sync(stub, readiness(other, closed=closed, pass_no=2))

        assert counts["unresolved"] == 1 and counts["resolved"] == 0
        assert counts["created"] == 1
        assert "✓ **1. A broker error is swallowed.** Fixed in `abc1234`" in stub.edited[7]
        assert stub.resolved == []
