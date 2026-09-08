"""Tests for the migration head-constant check."""

from __future__ import annotations

import pytest

from common.git import get_repo_root
from scripts.checks.repo import migration_check

REPO_ROOT = get_repo_root(__file__)


def test_real_repo_head_constant_is_in_sync() -> None:
    assert migration_check.run_migration_check(repo_root=REPO_ROOT) == 0


def test_stale_constant_fails(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(migration_check, "EXPECTED_HEAD_REVISION", "0000")
    assert migration_check.run_migration_check(repo_root=REPO_ROOT) == 1
    assert "EXPECTED_HEAD_REVISION" in capsys.readouterr().out


def test_advisory_mode_reports_without_failing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(migration_check, "EXPECTED_HEAD_REVISION", "0000")
    assert migration_check.run_migration_check(repo_root=REPO_ROOT, enforce=False) == 0
    assert "WARN" in capsys.readouterr().out
