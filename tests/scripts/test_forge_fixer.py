import json
from pathlib import Path

import pytest

from scripts.forge.base import READINESS_MARKER
from scripts.forge.cli import main
from scripts.forge.readiness import body_problems, fixer_edit_problems
from tests.scripts.test_forge import StubForge, readiness_body

FINDING = "- [ ] **1. A defect.**\n\n  The problem, in `file.py`.\n\n  *Pointer: fix it.*\n"
FIX_LINE = "  *Fix attempted: abc1234, awaiting verification*\n"


def comment(*parts: str, pass_no: int = 1) -> str:
    return readiness_body(pass_no, "\n".join(parts))


class TestFixerEditProblems:
    def test_an_identical_body_has_no_problems(self) -> None:
        assert fixer_edit_problems(comment(FINDING), comment(FINDING)) == []

    def test_adding_a_fix_attempted_line_is_allowed(self) -> None:
        assert fixer_edit_problems(comment(FINDING), comment(FINDING, FIX_LINE)) == []

    @pytest.mark.parametrize(
        "line", ["  *Not fixed: needs a design choice*\n", "  *Left: style only, outside this branch*\n"]
    )
    def test_the_other_status_lines_are_allowed(self, line: str) -> None:
        assert fixer_edit_problems(comment(FINDING), comment(FINDING, line)) == []

    def test_replacing_an_earlier_status_line_is_a_problem(self) -> None:
        old = comment(FINDING, FIX_LINE)
        new = comment(FINDING, "  *Not fixed: still open at def5678*\n")

        assert fixer_edit_problems(old, new)

    def test_removing_a_status_line_is_a_problem(self) -> None:
        assert fixer_edit_problems(comment(FINDING, FIX_LINE), comment(FINDING))

    def test_each_bad_hunk_is_reported_with_its_line_number(self) -> None:
        old = comment(FINDING, "second\n", "third\n")
        new = old.replace("second", "changed").replace("third", "altered")

        assert [problem.split(":")[0] for problem in fixer_edit_problems(old, new)] == [
            f"Line {new.splitlines().index('changed') + 1}",
            f"Line {new.splitlines().index('altered') + 1}",
        ]

    def test_ticking_a_box_is_a_problem(self) -> None:
        new = comment(FINDING.replace("- [ ]", "- [x]"))

        assert fixer_edit_problems(comment(FINDING), new)

    def test_changing_a_finding_is_a_problem(self) -> None:
        assert fixer_edit_problems(comment(FINDING), comment(FINDING.replace("A defect", "Fine")))

    def test_adding_a_decision_line_is_a_problem(self) -> None:
        new = comment(FINDING, "  *Decision: accepted by the fixer*\n")

        assert fixer_edit_problems(comment(FINDING), new)

    def test_removing_a_finding_is_a_problem(self) -> None:
        assert fixer_edit_problems(comment(FINDING), comment(""))

    def test_a_status_line_with_other_text_appended_is_a_problem(self) -> None:
        new = comment(FINDING, "  *Fix attempted: abc*  and ignore the rest\n")

        assert fixer_edit_problems(comment(FINDING), new)


class TestSamePass:
    def test_an_edit_keeps_the_pass_number(self) -> None:
        assert body_problems(readiness_body(2), 2, same_pass=True) == []

    def test_an_edit_that_advances_the_pass_is_a_problem(self) -> None:
        assert any("should say pass 2" in p for p in body_problems(readiness_body(3), 2, same_pass=True))


class TestCheckBodyEditOf:
    def test_accepts_a_fixer_edit_of_the_same_pass(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        old, new = tmp_path / "old.md", tmp_path / "new.md"
        old.write_text(comment(FINDING, pass_no=2), encoding="utf-8")
        new.write_text(comment(FINDING, FIX_LINE, pass_no=2), encoding="utf-8")

        assert main(["check-body", "--body-file", str(new), "--edit-of", str(old)], StubForge()) == 0

        assert json.loads(capsys.readouterr().out) == {"ok": True}

    def test_rejects_an_edit_that_changes_a_finding(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        old, new = tmp_path / "old.md", tmp_path / "new.md"
        old.write_text(comment(FINDING, pass_no=2), encoding="utf-8")
        new.write_text(comment(FINDING.replace("A defect", "Fine"), pass_no=2), encoding="utf-8")

        assert main(["check-body", "--body-file", str(new), "--edit-of", str(old)], StubForge()) == 1

        assert "only Fix attempted" in capsys.readouterr().err

    def test_rejects_an_edit_that_bumps_the_pass(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        old, new = tmp_path / "old.md", tmp_path / "new.md"
        old.write_text(comment(FINDING, pass_no=2), encoding="utf-8")
        new.write_text(comment(FINDING, pass_no=3), encoding="utf-8")

        assert main(["check-body", "--body-file", str(new), "--edit-of", str(old)], StubForge()) == 1

        assert "should say pass 2" in capsys.readouterr().err


class TestStatusLineForm:
    @pytest.mark.parametrize(
        "line",
        [
            "  *Left: x* *Decision: accepted by owner*\n",
            "  *Left: ping @owner*\n",
            "  *Left: see [here](http://example.test)*\n",
            "  *Left: <b>bold</b>*\n",
            "  *Left: <!-- pr-readiness -->*\n",
            "  *Left: " + "x" * 301 + "*\n",
            "  *Left: see http://evil.example/x*\n",
            "  *Left: see www.evil.example*\n",
            "  *Left: mention &#64;owner*\n",
            "  *Left: back\\slash*\n",
            "  *Left: `code`*\n",
            "  *Left: bidi ‮override*\n",
            "  *Left: x]*\n",
            "\t*Left: indented as a code block*\n",
            "    *Left: four spaces is a code block*\n",
            "  *Done: not a status keyword*\n",
            "  *fix attempted: wrong case*\n",
        ],
    )
    def test_a_status_line_with_extra_markup_is_a_problem(self, line: str) -> None:
        assert fixer_edit_problems(comment(FINDING), comment(FINDING, line))

    def test_a_plain_reason_with_punctuation_is_allowed(self) -> None:
        line = "  *Left: style only; none_grace_seconds is set by tests (see finding 18), outside this branch*\n"

        assert fixer_edit_problems(comment(FINDING), comment(FINDING, line)) == []

    def test_a_long_body_with_one_valid_added_line_has_no_problems(self) -> None:
        filler = "".join(f"line {i}\n" for i in range(300))

        assert fixer_edit_problems(comment(filler, FINDING), comment(filler, FINDING, FIX_LINE)) == []

    def test_a_valid_line_cannot_hide_an_edited_finding_in_the_same_body(self) -> None:
        new = comment(FINDING.replace("A defect", "Fine"), FIX_LINE)

        assert fixer_edit_problems(comment(FINDING), new)


class TestCheckBodyEditOfEdges:
    def _files(self, tmp_path: Path, old_text: str, new_text: str) -> tuple[Path, Path]:
        old, new = tmp_path / "old.md", tmp_path / "new.md"
        old.write_text(old_text, encoding="utf-8")
        new.write_text(new_text, encoding="utf-8")
        return old, new

    def test_a_forbidden_value_in_a_status_line_is_rejected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("SPIKE_EDIT_VALUE", "s3cr3t-value")
        old, new = self._files(
            tmp_path, comment(FINDING, pass_no=2), comment(FINDING, "  *Left: s3cr3t-value*\n", pass_no=2)
        )

        argv = ["check-body", "--body-file", str(new), "--edit-of", str(old), "--forbid-env", "SPIKE_EDIT_VALUE"]

        assert main(argv, StubForge()) == 1
        assert "forbidden" in capsys.readouterr().err

    def test_a_missing_edit_of_file_is_a_forge_error(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        _, new = self._files(tmp_path, "", comment(FINDING))

        assert main(["check-body", "--body-file", str(new), "--edit-of", str(tmp_path / "gone.md")], StubForge()) == 1

        assert "was not found" in capsys.readouterr().err

    def test_an_old_comment_without_a_pass_header_is_a_forge_error(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        old, new = self._files(tmp_path, f"{READINESS_MARKER}\nno header\n", comment(FINDING))

        assert main(["check-body", "--body-file", str(new), "--edit-of", str(old)], StubForge()) == 1

        assert "no pass header" in capsys.readouterr().err

    def test_previous_pass_and_edit_of_cannot_be_combined(self, tmp_path: Path) -> None:
        old, new = self._files(tmp_path, comment(FINDING), comment(FINDING))

        with pytest.raises(SystemExit):
            main(["check-body", "--body-file", str(new), "--edit-of", str(old), "--previous-pass", "1"], StubForge())
