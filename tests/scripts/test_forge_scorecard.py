import json
from collections.abc import Collection, Sequence

from scripts.forge import cli as cli_module
from scripts.forge.base import FINDING_MARKER, READINESS_MARKER, Comment
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
        assert "merged" in runner.calls[0] and "3" in runner.calls[0]

    def test_reactions_are_summed_per_finding_for_the_named_authors_only(self) -> None:
        def item(login: str, number: int, up: int, down: int) -> str:
            return json.dumps(
                {"author": login, "body": f"{FINDING_MARKER.format(number=number)}\nx", "up": up, "down": down}
            )

        output = "\n".join(
            [
                item("github-actions[bot]", 1, 2, 0),
                item("github-actions[bot]", 1, 1, 1),
                item("stranger", 1, 9, 9),
                json.dumps({"author": "github-actions[bot]", "body": "plain", "up": 5, "down": 5}),
            ]
        )
        runner = FakeRunner({"pulls/3/comments": output})

        reactions = GitHubForge(runner).finding_reactions(3, ["github-actions[bot]"])

        assert reactions == {1: (3, 1)}
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
