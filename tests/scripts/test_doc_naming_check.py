"""Tests for scripts.checks.docs.doc_naming_check."""

from __future__ import annotations

from pathlib import Path

from common.git import get_repo_root
from scripts.checks.docs.doc_naming_check import check_file, run_doc_naming_check
from tests.scripts.helpers import write_file


def _write(path: Path, content: str = "# Title\n\nBody.\n") -> Path:
    """Shared writer, plus the placeholder body most naming cases do not care about."""
    return write_file(path, content)


def test_kebab_case_doc_name_passes(tmp_path: Path) -> None:
    path = _write(tmp_path / "docs/reference/good-name.md")
    assert check_file(path, tmp_path).problems == []


def test_reserved_and_template_names_pass(tmp_path: Path) -> None:
    readme = _write(tmp_path / "docs/README.md")
    template = _write(tmp_path / "docs/adr/TEMPLATE.adr.md")

    assert check_file(readme, tmp_path).problems == []
    assert check_file(template, tmp_path).problems == []


def test_non_kebab_name_is_reported(tmp_path: Path) -> None:
    path = _write(tmp_path / "docs/reference/Bad_Name.md")

    assert check_file(path, tmp_path).problems == ["docs filename must be lowercase kebab-case `.md`"]


def test_adr_requires_numbered_prefix(tmp_path: Path) -> None:
    path = _write(tmp_path / "docs/adr/bad-adr.md")

    assert check_file(path, tmp_path).problems == ["ADR filename must be `NNN-kebab-case.md`"]


def test_adr_sequence_gap_is_allowed(tmp_path: Path) -> None:
    _write(tmp_path / "docs/adr/001-first.md")
    _write(tmp_path / "docs/adr/003-third.md")

    assert run_doc_naming_check(tmp_path, enforce=True) == 0


def test_duplicate_adr_number_is_reported(tmp_path: Path, capsys) -> None:
    _write(tmp_path / "docs/adr/001-first.md")
    _write(tmp_path / "docs/adr/001-second.md")

    assert run_doc_naming_check(tmp_path, enforce=True) == 1
    assert "duplicate ADR number 001" in capsys.readouterr().out


def test_advisory_mode_exits_zero_with_findings(tmp_path: Path) -> None:
    _write(tmp_path / "docs/reference/Bad_Name.md")

    assert run_doc_naming_check(tmp_path) == 0


def test_real_repo_doc_names_are_clean() -> None:
    repo_root = get_repo_root(Path(__file__))

    assert run_doc_naming_check(repo_root, enforce=True) == 0
