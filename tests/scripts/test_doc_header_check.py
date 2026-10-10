"""Tests for scripts.checks.docs.doc_header_check."""

from __future__ import annotations

from pathlib import Path

from common.git import get_repo_root
from scripts.checks.docs.doc_header_check import check_file, discover_docs, parse_header, run_doc_header_check
from tests.scripts.helpers import write_file

VALID_HEADER = (
    "# Some Doc\n"
    "\n"
    "Type: notes\n"
    "Status: Active\n"
    "Created: 2026-01-01\n"
    "Last Reviewed: 2026-07-02\n"
    "Purpose: One sentence.\n"
    "Related: [Other](other.md)\n"
    "\n"
    "Body text.\n"
)


def test_valid_header_has_no_problems(tmp_path: Path) -> None:
    doc = write_file(tmp_path / "docs/good.md", VALID_HEADER)
    assert check_file(doc).problems == []


def test_missing_and_empty_fields_are_reported(tmp_path: Path) -> None:
    doc = write_file(
        tmp_path / "docs/bad.md",
        "# Bad Doc\n\nType: notes\nStatus: Active\nPurpose: \n\nBody.\n",
    )
    problems = check_file(doc).problems
    assert "missing field: Created" in problems
    assert "missing field: Last Reviewed" in problems
    assert "empty field: Purpose" in problems


def test_unknown_type_and_status_are_reported(tmp_path: Path) -> None:
    doc = write_file(
        tmp_path / "docs/vocab.md",
        "# Vocab Doc\n\nType: essay\nStatus: WIP\nCreated: 2026-01-01\n"
        "Last Reviewed: 2026-07-02\nPurpose: X.\n\nBody.\n",
    )
    problems = check_file(doc).problems
    assert any("unknown Type: 'essay'" in p for p in problems)
    assert any("unknown Status: 'WIP'" in p for p in problems)


def test_status_suffix_after_valid_token_is_allowed(tmp_path: Path) -> None:
    doc = write_file(
        tmp_path / "docs/suffix.md",
        "# Suffix Doc\n\nType: implementation\nStatus: Ready (large; multi-commit)\n"
        "Created: 2026-01-01\nLast Reviewed: 2026-07-02\nPurpose: X.\n\nBody.\n",
    )
    assert check_file(doc).problems == []


def test_wrapped_field_values_are_tolerated(tmp_path: Path) -> None:
    doc = write_file(
        tmp_path / "docs/wrapped.md",
        "# Wrapped Doc\n\nType: notes\nStatus: Active\nCreated: 2026-01-01\n"
        "Last Reviewed: 2026-07-02\nPurpose: A long purpose that wraps to\n"
        "a second continuation line.\nRelated: [Other](other.md)\n\nBody.\n",
    )
    assert check_file(doc).problems == []


def test_non_iso_dates_are_reported(tmp_path: Path) -> None:
    doc = write_file(
        tmp_path / "docs/dates.md",
        "# Dates Doc\n\nType: notes\nStatus: Active\nCreated: Jan 1 2026\n"
        "Last Reviewed: 2026-07-02\nPurpose: X.\n\nBody.\n",
    )
    assert any("Created is not an ISO date" in p for p in check_file(doc).problems)


def test_missing_header_block_is_reported(tmp_path: Path) -> None:
    doc = write_file(tmp_path / "docs/none.md", "# Title Only\n\nJust body text, no header block.\n")
    problems = check_file(doc).problems
    assert any("missing field" in p for p in problems)


def test_parse_header_returns_none_without_h1(tmp_path: Path) -> None:
    assert parse_header("no title here\n") is None


def test_discover_docs_scopes_to_docs_and_skips_templates(tmp_path: Path) -> None:
    write_file(tmp_path / "docs/keep.md", VALID_HEADER)
    write_file(tmp_path / "docs/adr/TEMPLATE.adr.md", "# [Title]\n\nType: adr\n")
    write_file(tmp_path / "README.md", "# Root readme (out of scope)\n")
    names = {path.name for path in discover_docs(tmp_path)}
    assert names == {"keep.md"}


def test_run_advisory_exit_zero_with_findings(tmp_path: Path, capsys) -> None:
    write_file(tmp_path / "docs/bad.md", "# Bad\n\nBody only.\n")
    assert run_doc_header_check(tmp_path) == 0
    assert "WARN" in capsys.readouterr().out


def test_run_enforce_exit_one_with_findings(tmp_path: Path) -> None:
    write_file(tmp_path / "docs/bad.md", "# Bad\n\nBody only.\n")
    assert run_doc_header_check(tmp_path, enforce=True) == 1


def test_real_repo_docs_are_clean() -> None:
    repo_root = get_repo_root(Path(__file__))
    assert run_doc_header_check(repo_root, enforce=True) == 0
