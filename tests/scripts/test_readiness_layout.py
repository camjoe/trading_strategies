import re
from pathlib import Path

from scripts.forge.findings import open_counts, parse_findings, unhandled_open_findings, verdict
from scripts.forge.readiness import body_problems, pass_number

SKILL = Path(__file__).resolve().parents[2] / ".ai" / "skills" / "check-pr-readiness" / "SKILL.md"
COLLAPSED_SECTION = re.compile(r"<details>.*?</details>", re.DOTALL)
# The fenced layout under "Layout:" in Step 6 of the skill.
SKILL_LAYOUT = re.compile(r"\nLayout:\n\n```markdown\n(.*?)\n```", re.DOTALL)
# The lines that give a comment its structure: headings and the summaries of collapsed sections.
STRUCTURE_LINE = re.compile(r"^(?:#{2,4} .*|<summary>.*</summary>)$", re.MULTILINE)
COUNT = re.compile(r"<n>|\d+")

SAMPLE = """<!-- pr-readiness -->
## PR readiness: NOT READY

Reviewed `abc1234` against `develop` (`def5678`) · 2026-10-16 · pass 2 · current · Gate ✓ · CI ✓ 7 of 7

1 blockers · 1 concerns · 1 notes · 2 tests open · 1 closed. 1 blocker needs a fix.

#### 🔴 Blockers
- [ ] **1. A broker error is swallowed.** `src/x.py:10`: the guard error is caught, so a run continues. → Re-raise it. [Break it]

#### 🟠 Concerns
- [ ] **2. A runbook step fails.** `docs/y.md:5`: the command no longer exists. → Update it. [Architecture]
  *Fix attempted: 1234abc, awaiting verification*

<details>
<summary>🟡 Notes (1 open, optional): one line each</summary>

#### 🟡 Notes (1)
- [ ] **3. A name is public.** `src/x.py:3`: nothing outside uses it. → Make it private. [Simplifier]
  *Decision: Approved by the owner on 2026-10-16: keep it public.*

</details>

<details>
<summary>🧪 Tests (2 open, optional): gaps and extras. The code is not wrong; the tests could say more</summary>

#### 🧪 Tests (2)
- [ ] **4. Gap: no empty-list case.** `tests/test_x.py:20`: nothing pins an empty input. → Add one. [Test skeptic]
- [ ] **6. Extra: two tests repeat each other.** `tests/test_x.py:30`: both assert the same result. → Merge them. [Simplifier]

</details>

<details>
<summary>✓ Closed (1)</summary>

#### Closed (1)
- [x] **5. A path is wrong.** Fixed in `abc1234`: the link resolves.

</details>

### How to verify
Run `python -m scripts.run_checks quick`. Not yet true: nothing reports the failure to an operator.

<details>
<summary>Review details</summary>

Reviewers this pass: Architecture and conventions, Break it. Docs drift: no findings.
</details>
"""


def test_a_comment_in_the_layout_parses_for_the_fixer_loop_and_the_post_job() -> None:
    assert verdict(SAMPLE) == "NOT READY" and pass_number(SAMPLE) == 2
    assert body_problems(SAMPLE, 1) == []
    assert open_counts(SAMPLE) == {"blocker": 1, "concern": 1, "note": 3}
    assert [finding.number for finding in parse_findings(SAMPLE) if not finding.is_open] == [5]
    assert [finding.number for finding in unhandled_open_findings(SAMPLE)] == [1, 4, 6]


def _skill_layout() -> str:
    match = SKILL_LAYOUT.search(SKILL.read_text(encoding="utf-8").replace("\r", ""))
    assert match, "Step 6 of the skill no longer has a Layout block"
    return match.group(1)


def _structure(comment: str) -> list[str]:
    """The headings and summaries of *comment*, with every count normalized and the title's verdict left out."""
    lines = [COUNT.sub("N", line) for line in STRUCTURE_LINE.findall(comment)]
    return [line.split(":")[0] if line.startswith("## ") else line for line in lines]


def test_the_sample_has_the_same_structure_as_the_layout_in_the_skill() -> None:
    assert _structure(SAMPLE) == _structure(_skill_layout())


def test_how_to_verify_is_outside_every_collapsed_section_of_the_skills_layout() -> None:
    layout = _skill_layout()
    collapsed = "".join(COLLAPSED_SECTION.findall(layout))

    assert "### How to verify" in layout and "### How to verify" not in collapsed
    assert layout.index("### How to verify") < layout.index("<summary>Review details")
