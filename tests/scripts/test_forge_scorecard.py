import json
from collections import Counter
from collections.abc import Collection, Sequence
from pathlib import Path

from scripts.forge import cli as cli_module
from scripts.forge.base import FINDING_MARKER, READINESS_MARKER, Comment, ForgeError, PullRequestDetails
from scripts.forge.findings import parse_findings
from scripts.forge.github import GitHubForge
from scripts.forge.scorecard import LENSES, UNTAGGED, lenses_of, outcome_of, render_table, score_comment, tally
from tests.scripts.helpers import NEW_BODY

BODY = (
    f"{READINESS_MARKER}\n## PR readiness: READY\n\nReviewed `abc` · 2026-10-17 · pass 3 · current\n\n"
    "#### 🟠 Concerns\n"
    "- [ ] **7. Still open.** `src/a.py:1`: x. → y. [Break it (Opus), Operator]\n\n"
    "<details>\n<summary>🟡 Notes (1 open)</summary>\n\n#### 🟡 Notes (1)\n"
    "- [ ] **8. A note.** `src/a.py:2`: x. → y. [Break it, rated CONCERN; lowered to NOTE because unconfirmed]\n\n"
    "</details>\n\n"
    "<details>\n<summary>✓ Closed (4)</summary>\n\n#### Closed (4)\n"
    "- [x] **1. Fixed one.** Fixed in `abc1234`: the line is gone. [Break it, Test skeptic]\n"
    "- [x] **2. Decided one.** Decided: kept. [Simplifier]\n"
    "  *Decision: Approved by the owner on 2026-10-17: keep it.*\n"
    "- [x] **3. An old one.** Fixed in `abc1234`: done.\n"
    "- [x] **4. Two samples.** Fixed in `abc1234`: ok. [Break it x2, Architecture and conventions]\n"
    "</details>\n"
)


def finding(number: int):
    return next(f for f in parse_findings(BODY) if f.number == number)


class TestParts:
    def test_lenses_drop_model_and_sample_suffixes_and_the_lowering_clause(self) -> None:
        assert lenses_of(finding(7)) == ("Break it", "Operator")
        assert lenses_of(finding(8)) == ("Break it",)
        assert lenses_of(finding(4)) == ("Break it", "Architecture and conventions")

    def test_a_finding_with_no_tag_is_untagged(self) -> None:
        assert lenses_of(finding(3)) == (UNTAGGED,)

    def test_outcomes(self) -> None:
        assert outcome_of(finding(7)) == "left open"
        assert outcome_of(finding(1)) == "fixed"
        assert outcome_of(finding(2)) == "decided"


class TestTally:
    def test_each_lens_counts_the_findings_it_reported_by_outcome(self) -> None:
        rows = tally(score_comment(BODY))

        assert rows["Break it"]["findings"] == 4
        assert (rows["Break it"]["fixed"], rows["Break it"]["left open"]) == (2, 2)
        assert rows["Simplifier"]["decided"] == 1
        assert rows["Operator"]["left open"] == 1
        assert rows[UNTAGGED]["fixed"] == 1

    def test_reactions_are_counted_per_finding_and_lens(self) -> None:
        rows = tally(score_comment(BODY, {1: (2, 0), 7: (0, 1)}))

        assert (rows["Test skeptic"]["up"], rows["Test skeptic"]["down"]) == (2, 0)
        assert (rows["Operator"]["up"], rows["Operator"]["down"]) == (0, 1)
        assert (rows["Break it"]["up"], rows["Break it"]["down"]) == (2, 1)

    def test_the_table_lists_the_busiest_lens_first(self) -> None:
        table = render_table(tally(score_comment(BODY)))

        lines = table.splitlines()
        assert lines[0].startswith("lens")
        assert lines[1].startswith("Break it")


class FakeRunner:
    def __init__(self, responses: dict[str, str]) -> None:
        self.responses = responses
        self.calls: list[list[str]] = []

    def __call__(self, args: Sequence[str], stdin: str | None = None) -> str:
        self.calls.append(list(args))
        joined = " ".join(args)
        for fragment, output in self.responses.items():
            if fragment in joined:
                return output
        raise AssertionError(f"unexpected gh call: {joined}")


class TestGitHubScoring:
    def test_merged_pull_requests_are_listed_newest_first(self) -> None:
        runner = FakeRunner({"pr list": "318\n317\n316\n"})

        assert GitHubForge(runner).merged_pull_requests(3) == [318, 317, 316]

    def test_reactions_are_read_for_the_named_authors_only(self) -> None:
        def item(login: str, number: int, comment_id: int, up: int, down: int) -> str:
            return json.dumps(
                {
                    "id": comment_id,
                    "author": login,
                    "body": FINDING_MARKER.format(number=number) + "\nx",
                    "up": up,
                    "down": down,
                }
            )

        output = "\n".join(
            [
                item("github-actions[bot]", 1, 1, 2, 1),
                item("stranger", 1, 2, 9, 9),
                json.dumps({"id": 3, "author": "github-actions[bot]", "body": "plain", "up": 5, "down": 5}),
            ]
        )
        runner = FakeRunner({"pulls/3/comments": output})

        reactions = GitHubForge(runner).finding_reactions(3, ["github-actions[bot]"])

        assert reactions == {1: (2, 1)}
        assert "--paginate" in runner.calls[0]


class ScoreStub:
    def __init__(self, bodies: dict[int, str]) -> None:
        self.bodies = bodies

    def find_comment(self, number: int, authors: Collection[str]) -> Comment | None:
        assert "github-actions[bot]" in authors
        body = self.bodies.get(number)
        return None if body is None else Comment(1, body, "github-actions[bot]")

    def repository(self) -> str:
        return "owner/repo"

    def pull_request_details(self, number: int) -> PullRequestDetails:
        return PullRequestDetails(
            title=f"PR {number}",
            author="camjoe",
            base_ref="develop",
            head_ref="feature/x",
            created_at="2026-10-17T10:00:00Z",
            merged_at="2026-10-17T14:30:00Z",
            additions=30,
            deletions=4,
            commit_count=2,
            files=("src/a.py", "tests/test_a.py", "docs/a.md"),
        )

    def merged_pull_requests(self, limit: int) -> list[int]:
        return [20, 10][:limit]

    def finding_reactions(self, number: int, authors: Collection[str]) -> dict[int, tuple[int, int]]:
        return {1: (1, 0)}


class TestCli:
    def test_the_table_covers_every_named_and_merged_pull_request_once(self, capsys) -> None:
        stub = ScoreStub({20: BODY, 10: BODY, 5: BODY})

        code = cli_module.main(["review-scorecard", "--pr", "5", "--merged", "2"], forge=stub)  # type: ignore[arg-type]

        out = capsys.readouterr().out
        assert code == 0
        assert out.startswith("Scored 18 findings from 3 pull request(s).")
        assert "Break it" in out

    def test_json_output_lists_the_pull_requests_and_the_lens_counts(self, capsys) -> None:
        stub = ScoreStub({20: BODY})

        cli_module.main(["review-scorecard", "--pr", "20", "--json"], forge=stub)  # type: ignore[arg-type]

        data = json.loads(capsys.readouterr().out)
        assert data["pull_requests"] == [20]
        assert data["lenses"]["Break it"]["findings"] == 4

    def test_a_pull_request_with_no_readiness_comment_is_skipped(self, capsys) -> None:
        stub = ScoreStub({20: BODY})

        cli_module.main(["review-scorecard", "--pr", "99", "--pr", "20"], forge=stub)  # type: ignore[arg-type]

        assert capsys.readouterr().out.startswith("Scored 6 findings from 2 pull request(s).")

    def test_naming_no_pull_request_is_refused(self, capsys) -> None:
        code = cli_module.main(["review-scorecard"], forge=ScoreStub({}))  # type: ignore[arg-type]

        assert code == 1
        assert "Name pull requests" in capsys.readouterr().err

    def test_a_forge_that_cannot_score_is_refused(self, capsys) -> None:
        class Plain:
            pass

        code = cli_module.main(["review-scorecard", "--pr", "1"], forge=Plain())  # type: ignore[arg-type]

        assert code == 1
        assert "cannot score reviews" in capsys.readouterr().err


class TestScoringEdges:
    def _score(self, line: str):
        body = f"{READINESS_MARKER}\n## PR readiness: READY\n\nReviewed `a` · d · pass 1\n\n#### Closed (1)\n{line}\n"
        return parse_findings(body)[0]

    def test_a_closed_finding_that_says_neither_fixed_nor_decided_is_other(self) -> None:
        assert outcome_of(self._score("- [x] **1. Done.** Covered elsewhere. [Operator]")) == "other"

    def test_a_title_containing_decided_or_fixed_is_not_read_as_the_outcome(self) -> None:
        assert (
            outcome_of(self._score("- [x] **1. Decided ordering is wrong.** Fixed in `abc`: ok. [Operator]"))
            == "fixed"
        )
        assert outcome_of(self._score("- [x] **1. Fixed wording.** Decided: keep. [Operator]")) == "decided"

    def test_a_trailing_bracket_that_is_not_a_lens_name_is_not_a_lens(self) -> None:
        assert lenses_of(self._score("- [x] **1. Done.** Fixed in `abc`: see [x]")) == (UNTAGGED,)

    def test_other_findings_get_their_own_column(self) -> None:
        body = f"{READINESS_MARKER}\n## PR readiness: READY\n\nx\n\n#### Closed (1)\n- [x] **1. Done.** Covered. [Operator]\n"

        rows = tally(score_comment(body))

        assert rows["Operator"]["other"] == 1
        assert " other " in render_table(rows).splitlines()[0]
        assert rows["Operator"]["findings"] == sum(
            rows["Operator"][k] for k in ("fixed", "decided", "left open", "other")
        )


class TestGitHubArguments:
    def test_the_merged_listing_asks_for_numbers_only(self) -> None:
        runner = FakeRunner({"pr list": "1\n"})

        GitHubForge(runner).merged_pull_requests(5)

        assert runner.calls[0] == [
            "pr",
            "list",
            "--state",
            "merged",
            "--limit",
            "5",
            "--json",
            "number",
            "--jq",
            ".[].number",
        ]

    def test_the_reactions_query_reads_the_fields_the_code_uses(self) -> None:
        runner = FakeRunner({"pulls/3/comments": ""})

        GitHubForge(runner).finding_reactions(3, ["github-actions[bot]"])

        jq = runner.calls[0][-1]
        for field in ("id: .id", "author: .user.login", "body: .body", '.reactions["+1"]', '.reactions["-1"]'):
            assert field in jq

    def test_only_the_latest_comment_of_a_finding_counts(self) -> None:
        def item(comment_id: int, up: int) -> str:
            body = f"{FINDING_MARKER.format(number=1)}\nx"
            return json.dumps({"id": comment_id, "author": "github-actions[bot]", "body": body, "up": up, "down": 0})

        runner = FakeRunner({"pulls/3/comments": item(10, 5) + "\n" + item(20, 1)})

        assert GitHubForge(runner).finding_reactions(3, ["github-actions[bot]"]) == {1: (1, 0)}


class TestCliEdges:
    def test_the_reactions_belong_to_the_pull_request_they_were_read_for(self, capsys) -> None:
        class Recording(ScoreStub):
            def __init__(self, bodies: dict[int, str]) -> None:
                super().__init__(bodies)
                self.reaction_calls: list[tuple[int, tuple[str, ...]]] = []
                self.comment_authors: list[tuple[str, ...]] = []

            def find_comment(self, number: int, authors: Collection[str]) -> Comment | None:
                self.comment_authors.append(tuple(authors))
                return Comment(1, self.bodies[number], "me")

            def finding_reactions(self, number: int, authors: Collection[str]) -> dict[int, tuple[int, int]]:
                self.reaction_calls.append((number, tuple(authors)))
                return {1: (number, 0)}

        stub = Recording({4: BODY, 9: BODY})

        cli_module.main(["review-scorecard", "--pr", "4", "--pr", "9", "--author", "me", "--json"], forge=stub)  # type: ignore[arg-type]

        data = json.loads(capsys.readouterr().out)
        assert [call[0] for call in stub.reaction_calls] == [4, 9]
        assert {call[1] for call in stub.reaction_calls} == {("me",)}
        assert data["lenses"]["Test skeptic"]["up"] == 13

    def test_a_negative_merged_count_is_refused(self, capsys) -> None:
        code = cli_module.main(["review-scorecard", "--merged", "-1"], forge=ScoreStub({}))  # type: ignore[arg-type]

        assert code == 1
        assert "must not be negative" in capsys.readouterr().err

    def test_one_failing_pull_request_is_reported_and_the_rest_are_still_scored(self, capsys) -> None:
        class Flaky(ScoreStub):
            def find_comment(self, number: int, authors: Collection[str]) -> Comment | None:
                if number == 5:
                    raise ForgeError("gh pr failed")
                return super().find_comment(number, authors)

        code = cli_module.main(["review-scorecard", "--pr", "5", "--pr", "20"], forge=Flaky({20: BODY}))  # type: ignore[arg-type]

        captured = capsys.readouterr()
        assert code == 1
        assert captured.out.startswith("Scored 6 findings from 1 pull request(s).")
        assert "Could not read #5: gh pr failed" in captured.err

    def test_a_failure_while_reading_reactions_is_also_reported(self, capsys) -> None:
        class NoReactions(ScoreStub):
            def finding_reactions(self, number: int, authors: Collection[str]) -> dict[int, tuple[int, int]]:
                raise ForgeError("reactions failed")

        code = cli_module.main(["review-scorecard", "--pr", "20", "--json"], forge=NoReactions({20: BODY}))  # type: ignore[arg-type]

        data = json.loads(capsys.readouterr().out)
        assert code == 1
        assert data["pull_requests"] == [] and data["skipped"] == {"20": "reactions failed"}

    def test_a_pull_request_named_and_merged_is_scored_once(self, capsys) -> None:
        stub = ScoreStub({20: BODY, 10: BODY})

        cli_module.main(["review-scorecard", "--pr", "20", "--merged", "2", "--json"], forge=stub)  # type: ignore[arg-type]

        assert json.loads(capsys.readouterr().out)["pull_requests"] == [20, 10]


class TestMoreEdges:
    def _closed(self, line: str):
        body = f"{READINESS_MARKER}\n## PR readiness: READY\n\nx\n\n#### Closed (1)\n{line}\n"
        return parse_findings(body)[0]

    def test_only_known_lens_names_count_and_aliases_and_stacked_suffixes_are_cleaned(self) -> None:
        assert lenses_of(self._closed("- [x] **1. T.** Fixed in `a`: ok. [Unreleased]")) == (UNTAGGED,)
        assert lenses_of(self._closed("- [x] **1. T.** Fixed in `a`: ok. [Break it (opus) x2]")) == ("Break it",)
        assert lenses_of(self._closed("- [x] **1. T.** Fixed in `a`: ok. [Architecture]")) == (
            "Architecture and conventions",
        )

    def test_a_decision_line_alone_makes_a_closed_finding_decided(self) -> None:
        line = "- [x] **1. T.** Fixed in `a`: ok. [Operator]\n  *Decision: Approved by the owner on 2026-10-17: keep.*"

        assert outcome_of(self._closed(line)) == "decided"

    def test_a_title_with_bold_text_still_reads_the_outcome_after_the_title(self) -> None:
        assert outcome_of(self._closed("- [x] **1. The **bold** word.** Fixed in `a`: ok. [Operator]")) == "fixed"

    def test_equal_counts_are_listed_by_name(self) -> None:
        rows = {"Zed": Counter(findings=1), "Alpha": Counter(findings=1)}

        names = [line.split()[0] for line in render_table(rows).splitlines()[1:]]

        assert names == ["Alpha", "Zed"]

    def test_the_comments_endpoint_call_is_exact(self) -> None:
        runner = FakeRunner({"pulls/3/comments": ""})

        GitHubForge(runner).finding_reactions(3, ["github-actions[bot]"])

        assert runner.calls[0][:3] == ["api", "repos/{owner}/{repo}/pulls/3/comments", "--paginate"]

    def test_the_latest_comment_wins_even_when_the_ids_arrive_in_descending_order(self) -> None:
        def item(comment_id: int, up: int) -> str:
            body = FINDING_MARKER.format(number=1) + "\nx"
            return json.dumps({"id": comment_id, "author": "github-actions[bot]", "body": body, "up": up, "down": 0})

        runner = FakeRunner({"pulls/3/comments": item(20, 1) + "\n" + item(10, 5)})

        assert GitHubForge(runner).finding_reactions(3, ["github-actions[bot]"]) == {1: (1, 0)}


class TestRepliesAreNotFindings:
    def test_the_reactions_query_skips_replies(self) -> None:
        runner = FakeRunner({"pulls/3/comments": ""})

        GitHubForge(runner).finding_reactions(3, ["github-actions[bot]"])

        assert "select(.in_reply_to_id == null)" in runner.calls[0][-1]


class TestNames:
    def _closed(self, line: str):
        body = f"{READINESS_MARKER}\n## PR readiness: READY\n\nx\n\n#### Closed (1)\n{line}\n"
        return parse_findings(body)[0]

    def test_lens_names_ignore_case_and_nested_suffixes(self) -> None:
        assert lenses_of(self._closed("- [x] **1. T.** Fixed in `a`: ok. [Break It]")) == ("Break it",)
        assert lenses_of(self._closed("- [x] **1. T.** Fixed in `a`: ok. [Operator (a (b))]")) == ("Operator",)

    def test_a_title_ending_in_a_question_mark_is_stripped_before_reading_the_outcome(self) -> None:
        assert outcome_of(self._closed("- [x] **3. Why is X?** Fixed in `a`: ok. [Operator]")) == "fixed"

    def test_every_lens_the_scorecard_knows_is_named_in_the_lens_guide(self) -> None:
        guide = (Path(__file__).resolve().parents[2] / ".ai" / "skills" / "code-review" / "lenses.md").read_text(
            encoding="utf-8"
        )

        for lens in LENSES:
            if lens != "Orchestrator":
                assert lens in guide, lens


class TestSpellings:
    def _closed(self, line: str):
        body = f"{READINESS_MARKER}\n## PR readiness: READY\n\nx\n\n#### Closed (1)\n{line}\n"
        return parse_findings(body)[0]

    def test_accepted_lens_spellings(self) -> None:
        for tag, expected in (
            ("Break it(2)", ("Break it",)),
            ("Break it X2", ("Break it",)),
            ("Operator x2 x3", ("Operator",)),
            ("architecture", ("Architecture and conventions",)),
            ("Break it (Opus) x2", ("Break it",)),
            ("Test Skeptic", ("Test skeptic",)),
        ):
            assert lenses_of(self._closed(f"- [x] **1. T.** Fixed in `a`: ok. [{tag}]")) == expected, tag

    def test_titles_ending_in_a_period_question_mark_or_exclamation_mark(self) -> None:
        for title in ("A thing.", "Why is X?", "Never do this!"):
            assert outcome_of(self._closed(f"- [x] **1. {title}** Fixed in `a`: ok. [Operator]")) == "fixed", title


class TestMetadata:
    def test_area_of_a_path(self) -> None:
        from scripts.forge.scorecard import area_of

        cases = {
            "src/a/b.py": "code",
            "tests/scripts/test_x.py": "tests",
            "pkg/test_x.py": "tests",
            "pkg/x_test.py": "tests",
            "docs/runbooks/a.md": "docs",
            "README.md": "docs",
            ".github/workflows/x.yml": "ci",
            ".ai/skills/x/SKILL.md": "agent",
            "AGENTS.md": "agent",
            "config/app.toml": "config",
        }
        for path, area in cases.items():
            assert area_of(path) == area, path

    def test_a_finding_carries_its_title_path_line_area_fix_and_lowering(self) -> None:
        body = (
            f"{READINESS_MARKER}\n## PR readiness: READY\n\nReviewed `a` · d · pass 2 · current\n\n"
            "<details>\n<summary>🟡 Notes</summary>\n\n#### 🟡 Notes (1)\n"
            "- [ ] **8. Why is it wrong?** `src/x.py:12`: text. → fix. "
            "[Break it, rated CONCERN; lowered to NOTE because unconfirmed]\n\n</details>\n\n"
            "<details>\n<summary>✓ Closed (1)</summary>\n\n#### Closed (1)\n"
            "- [x] **1. A broker error.** Fixed in `abc1234`: ok. [Operator]\n</details>\n"
        )

        found = {f.number: f for f in score_comment(body)}

        note = found[8]
        assert (note.title, note.path, note.line, note.area) == ("Why is it wrong?", "src/x.py", 12, "code")
        assert note.lowered == "unconfirmed" and note.fixed_in is None
        assert note.text.startswith("**8. Why is it wrong?**")
        closed = found[1]
        assert closed.fixed_in == "abc1234" and closed.path is None and closed.area is None

    def test_a_fix_named_without_backticks_gives_its_sha(self) -> None:
        body = f"{READINESS_MARKER}\n## PR readiness: READY\n\nx\n\n#### Closed (1)\n- [x] **1. T.** Fixed in abc1234: ok. [Operator]\n"

        assert score_comment(body)[0].fixed_in == "abc1234"

    def test_details_are_fetched_only_when_asked(self) -> None:
        calls: list[int] = []

        class Counting(ScoreStub):
            def pull_request_details(self, number: int) -> PullRequestDetails:
                calls.append(number)
                return super().pull_request_details(number)

        from scripts.forge.scorecard import collect_scores

        stub = Counting({20: BODY})
        scores, _, _ = collect_scores(stub, [20], ["github-actions[bot]"])
        assert calls == [] and scores[20].details is None

        scores, _, _ = collect_scores(stub, [20], ["github-actions[bot]"], with_details=True)
        assert calls == [20] and scores[20].details is not None and scores[20].details.author == "camjoe"


class TestMetadataEdges:
    def test_a_range_anchor_gives_its_first_line(self) -> None:
        body = (
            f"{READINESS_MARKER}\n## PR readiness: READY\n\nx\n\n#### 🟡 Notes (1)\n"
            "- [ ] **2. A range.** `src/a.py:3-9`: x. → y. [Operator]\n"
        )

        assert (score_comment(body)[0].path, score_comment(body)[0].line) == ("src/a.py", 3)

    def test_a_fix_described_in_prose_has_no_sha(self) -> None:
        body = f"{READINESS_MARKER}\n## PR readiness: READY\n\nx\n\n#### Closed (1)\n- [x] **1. T.** Fixed in the next commit: ok. [Operator]\n"

        assert score_comment(body)[0].fixed_in is None

    def test_a_finding_with_no_title_match_has_an_empty_title(self) -> None:
        body = f"{READINESS_MARKER}\n## PR readiness: READY\n\nx\n\n#### Closed (1)\n- [x] no title here. [Operator]\n"

        assert score_comment(body) == []


class TestNewFormat:
    def _found(self):
        return {f.number: f for f in score_comment(NEW_BODY)}

    def test_the_predicted_need_the_kind_and_the_opening_pass_are_read_from_an_open_finding(self) -> None:
        concern = self._found()[4]

        assert (concern.needs, concern.kind, concern.opened_pass) == ("decision", "design", 2)
        assert concern.lenses == ("Break it", "Operator")
        assert (concern.path, concern.line, concern.area) == ("src/a.py", 7, "code")

    def test_a_lowered_note_keeps_its_reason_kind_and_pass_without_the_tag_noise(self) -> None:
        note = self._found()[5]

        assert note.lowered == "unconfirmed"
        assert (note.needs, note.kind, note.opened_pass) == ("info", "bug", 3)
        assert note.lenses == ("Break it",)

    def test_a_closed_finding_says_who_closed_it_and_in_which_pass(self) -> None:
        found = self._found()

        assert (found[1].closed_by, found[1].closed_pass, found[1].fixed_in) == ("fixer", 2, "abc1234")
        assert (found[2].closed_by, found[2].closed_pass, found[2].outcome) == ("author", 3, "fixed")
        assert (found[3].closed_by, found[3].closed_pass, found[3].outcome) == ("owner", 3, "decided")

    def test_a_closed_finding_keeps_its_path_and_area_and_reads_its_outcome_after_the_anchor(self) -> None:
        found = self._found()

        assert (found[1].path, found[1].area, found[1].outcome) == ("src/a.py", "code", "fixed")
        assert (found[2].path, found[2].area) == ("docs/a.md", "docs")
        assert found[3].kind == "wording" and found[3].opened_pass == 2

    def test_findings_in_the_old_format_have_no_new_fields(self) -> None:
        old = f"{READINESS_MARKER}\n## PR readiness: READY\n\nx\n\n#### Closed (1)\n- [x] **1. T.** Fixed in `abc1234`: ok. [Operator]\n"

        finding = score_comment(old)[0]

        assert (finding.kind, finding.needs, finding.opened_pass, finding.closed_pass, finding.closed_by) == (
            None,
        ) * 5
        assert finding.lenses == ("Operator",)

    def test_a_repeated_finding_number_is_counted_once_in_the_live_tally_too(self) -> None:
        body = (
            f"{READINESS_MARKER}\n## PR readiness: READY\n\nx\n\n#### 🟡 Notes (2)\n"
            "- [ ] **1. First.** `a.py:1`: x. → fix: y. [Operator]\n- [ ] **1. Again.** `a.py:2`: x. → fix: y. [Operator]\n"
        )

        assert [f.title for f in score_comment(body)] == ["Again"]

    def test_the_human_table_has_a_row_per_prediction_and_a_column_per_ending(self) -> None:
        from scripts.forge.scorecard import render_human_table

        table = render_human_table({("decision", "author"): 2, ("fix", "fixer"): 1})

        lines = table.splitlines()
        assert lines[0].split() == ["predicted", "fixer", "author", "owner", "left", "open", "(not", "recorded)"]
        assert lines[1].split()[:3] == ["fix", "1", "0"] and lines[2].split()[:4] == ["decision", "0", "2", "0"]


class TestTagFromTheRight:
    def _open(self, tag: str):
        body = f"{READINESS_MARKER}\n## PR readiness: READY\n\nx\n\n#### 🟡 Notes (1)\n- [ ] **1. T.** `a.py:1`: x. → fix: y. [{tag}]\n"
        return parse_findings(body)[0]

    def test_a_lowered_reason_may_contain_the_separator(self) -> None:
        scored = score_comment(
            f"{READINESS_MARKER}\n## PR readiness: READY\n\nx\n\n#### 🟡 Notes (1)\n"
            "- [ ] **1. T.** `a.py:1`: x. → fix: y. [Break it, rated CONCERN; lowered to NOTE because a · b · bug · pass 2]\n"
        )[0]

        assert scored.lowered == "a · b"
        assert (scored.kind, scored.opened_pass) == ("bug", 2)

    def test_a_tag_with_only_a_kind_or_only_a_pass_is_read(self) -> None:
        only_kind = score_comment(
            f"{READINESS_MARKER}\n## PR readiness: READY\n\nx\n\n#### 🟡 Notes (1)\n- [ ] **1. T.** `a.py:1`: x. → fix: y. [Operator · docs]\n"
        )[0]
        only_pass = score_comment(
            f"{READINESS_MARKER}\n## PR readiness: READY\n\nx\n\n#### 🟡 Notes (1)\n- [ ] **1. T.** `a.py:1`: x. → fix: y. [Operator · pass 4]\n"
        )[0]

        assert (only_kind.kind, only_kind.opened_pass, only_kind.lenses) == ("docs", None, ("Operator",))
        assert (only_pass.kind, only_pass.opened_pass) == (None, 4)


class TestPredictionOnClosedLines:
    def _closed(self, tag: str):
        body = (
            f"{READINESS_MARKER}\n## PR readiness: READY\n\nx\n\n#### Closed (1)\n"
            f"- [x] **1. T.** `a.py:1`: Fixed in `abc1234` (pass 2, by author): ok. [{tag}]\n"
        )
        return score_comment(body)[0]

    def test_a_closed_line_gives_its_predicted_need_from_the_tag(self) -> None:
        finding = self._closed("Operator · bug · decision · pass 1")

        assert (finding.needs, finding.kind, finding.opened_pass, finding.lenses) == (
            "decision",
            "bug",
            1,
            ("Operator",),
        )

    def test_a_closed_line_in_the_earlier_layout_has_no_predicted_need(self) -> None:
        finding = self._closed("Operator · bug · pass 1")

        assert finding.needs is None and finding.kind == "bug"

    def test_the_tag_is_read_from_the_right_whatever_is_missing(self) -> None:
        assert self._closed("Operator · fix").needs == "fix"
        assert self._closed("Operator · bug · info").kind == "bug"
        assert self._closed("Operator · info · pass 3").opened_pass == 3

    def test_an_open_finding_takes_the_need_from_its_hint(self) -> None:
        body = (
            f"{READINESS_MARKER}\n## PR readiness: READY\n\nx\n\n#### 🟡 Notes (1)\n"
            "- [ ] **1. T.** `a.py:1`: x. → info: what does the host run? [Operator · design · pass 2]\n"
        )

        assert score_comment(body)[0].needs == "info"
