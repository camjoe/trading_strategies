import json
from collections import Counter
from collections.abc import Collection, Sequence

from scripts.forge import cli as cli_module
from scripts.forge.base import FINDING_MARKER, READINESS_MARKER, Comment, ForgeError
from scripts.forge.findings import parse_findings
from scripts.forge.github import GitHubForge
from scripts.forge.scorecard import UNTAGGED, lenses_of, outcome_of, render_table, score_comment, tally

BODY = (
    f"{READINESS_MARKER}\n## PR readiness: READY\n\nReviewed `abc` · 2026-10-17 · pass 3\n\n"
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
