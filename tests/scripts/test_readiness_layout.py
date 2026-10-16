import re
from pathlib import Path

from scripts.forge.findings import open_counts, parse_findings, unhandled_open_findings, verdict
from scripts.forge.readiness import body_problems, pass_number

SKILL = Path(__file__).resolve().parents[2] / ".ai" / "skills" / "check-pr-readiness" / "SKILL.md"
COLLAPSED_SECTION = re.compile(r"<details>.*?</details>", re.DOTALL)

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


def test_how_to_verify_is_outside_every_collapsed_section() -> None:
    collapsed = "".join(COLLAPSED_SECTION.findall(SAMPLE))

    assert "### How to verify" in SAMPLE and "### How to verify" not in collapsed


def test_the_skill_describes_the_layout_and_no_longer_asks_for_the_dropped_sections() -> None:
    skill = SKILL.read_text(encoding="utf-8")

    for summary in ("<summary>🟡 Notes", "<summary>🧪 Tests", "<summary>✓ Closed", "<summary>Review details"):
        assert summary in skill
    assert skill.index("### How to verify") < skill.index("<summary>Review details")
    assert "Pass history" not in skill and "Cleanup and obsolescence" not in skill and "| Step | Result |" not in skill
