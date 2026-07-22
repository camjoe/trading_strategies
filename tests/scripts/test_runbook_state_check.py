"""Tests for scripts.checks.docs.runbook_state_check."""

from __future__ import annotations

from pathlib import Path

from common.paths.repo_paths import get_repo_root
from scripts.checks.docs.runbook_state_check import check_file, run_runbook_state_check


def _write_runbook(repo_root: Path, content: str) -> Path:
    path = repo_root / "docs" / "runbooks" / "example.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_blank_checklist_and_generic_instructions_pass(tmp_path: Path) -> None:
    path = _write_runbook(tmp_path, "# Runbook\n\n- [ ] Verify the timer on the host.\n")

    assert check_file(path).problems == []


def test_completed_checkbox_is_reported(tmp_path: Path) -> None:
    path = _write_runbook(tmp_path, "# Runbook\n\n- [x] Timer installed.\n")

    assert "completed checklist item" in check_file(path).problems[0]


def test_dated_verification_and_host_state_are_reported(tmp_path: Path) -> None:
    path = _write_runbook(
        tmp_path,
        "# Runbook\n\nSetup already applied on this host and verified 2026-07-21.\n",
    )

    problems = check_file(path).problems
    assert any("dated machine verification" in problem for problem in problems)
    assert any("machine-specific state phrase" in problem for problem in problems)


def test_literal_operational_schedule_is_reported(tmp_path: Path) -> None:
    path = _write_runbook(
        tmp_path,
        "# Runbook\n\ncommand --daily-paper-trading-time 13:00 --health-check-time 13:35\n",
    )

    assert any("literal operational schedule" in problem for problem in check_file(path).problems)


def test_enforced_check_fails_with_operator_state(tmp_path: Path) -> None:
    _write_runbook(tmp_path, "# Runbook\n\n- [X] Host configured.\n")

    assert run_runbook_state_check(tmp_path, enforce=True) == 1


def test_runtime_jobs_reference_is_checked_for_literal_schedule(tmp_path: Path) -> None:
    path = tmp_path / "docs" / "reference" / "runtime-jobs.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# Runtime Jobs\n\ncommand --weekly-db-backup-time 12:58\n", encoding="utf-8")

    assert run_runbook_state_check(tmp_path, enforce=True) == 1


def test_real_repo_runbooks_are_clean() -> None:
    repo_root = get_repo_root(Path(__file__))

    assert run_runbook_state_check(repo_root, enforce=True) == 0
