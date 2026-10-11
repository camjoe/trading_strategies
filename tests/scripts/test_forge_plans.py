from pathlib import Path

from scripts.forge.plans import (
    Plan,
    claimed_plan_branch,
    claimed_plan_text,
    claimed_readme_text,
    parse_plan,
    pickup_problems,
    plans_claimed_by,
    readme_without_row,
)

PLAN = """# Plan: per-contract trading rules (order increment)

Status: drafted 2026-10-09. Not started. The IBKR rules endpoint has NOT been checked on the host.
Branch to use: `feature/contract-trading-rules`, off `develop`, after #294 merges.

## Depends on
- PR #294
"""

README = """# plan/

## Index
| Plan | Status | Depends on |
|---|---|---|
| [contract-trading-rules.md](contract-trading-rules.md) | Drafted 2026-10-09. Not checked on the host. | PR #294 merged |
| [more-trading-evidence.md](more-trading-evidence.md) | Drafted 2026-10-09. | none (related plan) |
"""


def write(tmp_path: Path, plan_text: str = PLAN, name: str = "contract-trading-rules.md") -> tuple[Path, Path]:
    plan, readme = tmp_path / name, tmp_path / "README.md"
    plan.write_text(plan_text, encoding="utf-8")
    readme.write_text(README, encoding="utf-8")
    return plan, readme


class TestLoadPlan:
    def test_reads_title_status_branch_and_dependencies(self, tmp_path: Path) -> None:
        plan = load_plan(*write(tmp_path))

        assert plan.title == "per-contract trading rules (order increment)"
        assert plan.status.startswith("drafted 2026-10-09")
        assert plan.branch == "feature/contract-trading-rules"
        assert plan.depends_on == "PR #294 merged"

    def test_the_branch_defaults_to_feature_and_the_file_stem(self, tmp_path: Path) -> None:
        plan = load_plan(*write(tmp_path, "# Plan: x\n\nStatus: drafted.\n", "more-trading-evidence.md"))

        assert plan.branch == "feature/more-trading-evidence"
        assert plan.depends_on == "none (related plan)"

    def test_a_plan_missing_from_the_index_has_unknown_dependencies(self, tmp_path: Path) -> None:
        assert load_plan(*write(tmp_path, name="unlisted.md")).depends_on is None


def make(**overrides: str | None) -> Plan:
    values = {"file": "p.md", "title": "t", "status": "drafted.", "branch": "feature/p", "depends_on": "none"}
    return Plan(**{**values, **overrides})  # type: ignore[arg-type]


class TestPickupProblems:
    def test_a_drafted_plan_with_no_dependencies_can_be_picked_up(self) -> None:
        assert pickup_problems(make()) == []

    def test_a_plan_already_in_progress_is_refused(self) -> None:
        assert any("Already in progress" in p for p in pickup_problems(make(status="In progress (branch `x`).")))

    def test_a_blocked_plan_is_refused(self) -> None:
        assert any("Blocked" in p for p in pickup_problems(make(status="blocked on the host check")))

    def test_dependencies_must_be_confirmed(self) -> None:
        assert any("depends on" in p for p in pickup_problems(make(depends_on="PR #294 merged")))
        assert pickup_problems(make(depends_on="PR #294 merged"), depends_ok=True) == []

    def test_a_plan_missing_from_the_index_is_refused(self) -> None:
        assert any("not listed" in p for p in pickup_problems(make(depends_on=None), depends_ok=True))

    def test_the_index_itself_is_refused(self) -> None:
        assert pickup_problems(make(file="README.md"))

    def test_an_unusable_branch_name_is_refused(self) -> None:
        assert pickup_problems(make(branch="feature/../x"))
        assert pickup_problems(make(branch="bad name"))


class TestClaiming:
    def test_the_status_line_becomes_a_claim_and_keeps_what_it_said(self) -> None:
        text = claimed_plan_text(PLAN, "feature/contract-trading-rules")

        assert "Status: in progress (branch `feature/contract-trading-rules`)." in text
        assert "NOT been checked on the host" in text
        assert "Branch to use: `feature/contract-trading-rules`, off `develop`" in text
        assert text.count("Status:") == 1

    def test_a_multi_line_status_is_replaced_whole(self) -> None:
        plan = "# Plan: x\n\nStatus: drafted.\nNot started. More text\non a third line.\n\n## Goal\nBody\n"

        text = claimed_plan_text(plan, "feature/x")

        assert "on a third line" in " ".join(text.split())
        assert "## Goal\nBody" in text
        assert text.count("Status:") == 1

    def test_a_plan_without_a_status_line_is_unchanged(self) -> None:
        assert claimed_plan_text("# Plan: x\n", "feature/x") == "# Plan: x\n"

    def test_only_the_named_index_row_changes(self) -> None:
        text = claimed_readme_text(README, "contract-trading-rules.md", "feature/contract-trading-rules")

        assert "| [contract-trading-rules.md](contract-trading-rules.md) | in progress (branch `feature/" in text
        assert (
            "| [more-trading-evidence.md](more-trading-evidence.md) | Drafted 2026-10-09. | none (related plan) |"
            in text
        )
        assert text.count("PR #294 merged |") == 1


class TestClaimedHelpers:
    def test_the_branch_that_claimed_a_plan_is_read_from_its_status(self) -> None:
        text = claimed_plan_text(PLAN, "feature/contract-trading-rules")

        assert claimed_plan_branch(text) == "feature/contract-trading-rules"

    def test_an_unclaimed_or_differently_phrased_status_is_not_a_claim(self) -> None:
        assert claimed_plan_branch(PLAN) is None
        assert claimed_plan_branch("Status: in progress. Branch: `plan/x` (PR 301).\n") is None

    def test_an_index_row_can_be_removed_without_touching_the_others(self) -> None:
        text = readme_without_row(README, "contract-trading-rules.md")

        assert "contract-trading-rules.md" not in text
        assert "more-trading-evidence.md" in text and "| Plan | Status | Depends on |" in text

    def test_removing_a_row_that_is_not_there_changes_nothing(self) -> None:
        assert readme_without_row(README, "missing.md") == README

    def test_only_plans_claimed_by_the_named_branch_are_found(self, tmp_path: Path) -> None:
        (tmp_path / "a.md").write_text(claimed_plan_text(PLAN, "feature/a"), encoding="utf-8")
        (tmp_path / "b.md").write_text(claimed_plan_text(PLAN, "feature/b"), encoding="utf-8")
        (tmp_path / "c.md").write_text(PLAN, encoding="utf-8")
        (tmp_path / "README.md").write_text(claimed_plan_text(PLAN, "feature/a"), encoding="utf-8")

        assert [path.name for path in plans_claimed_by(tmp_path, "feature/a")] == ["a.md"]
        assert plans_claimed_by(tmp_path, "feature/none") == []


def load_plan(plan_file: Path, readme: Path) -> Plan:
    return parse_plan(plan_file.name, plan_file.read_text(encoding="utf-8"), readme.read_text(encoding="utf-8"))
