"""Tests for scripts.checks.repo.live_safety_check."""

from __future__ import annotations

from pathlib import Path

from common.git import get_repo_root
from scripts.checks.repo.live_safety_check import check_file, run_live_safety_check
from tests.scripts.helpers import write_file


def test_dict_enablement_is_reported(tmp_path: Path) -> None:
    path = write_file(tmp_path / "tests/example.py", "row = {'live_trading_enabled': 1}\n")

    findings = check_file(path)

    assert len(findings) == 1
    assert findings[0].message == "maps live_trading_enabled to true/1"


def test_keyword_enablement_is_reported(tmp_path: Path) -> None:
    path = write_file(tmp_path / "src/example.py", "build_account(live_trading_enabled=True)\n")

    findings = check_file(path)

    assert len(findings) == 1
    assert findings[0].message == "passes live_trading_enabled=true/1"


def test_sql_literal_enablement_is_reported(tmp_path: Path) -> None:
    path = write_file(
        tmp_path / "scripts/example.py",
        'SQL = "UPDATE accounts SET live_trading_enabled = 1 WHERE id = ?"\n',
    )

    findings = check_file(path)

    assert len(findings) == 1
    assert findings[0].message == "string literal enables live_trading_enabled"


def test_docstring_mentions_are_not_reported(tmp_path: Path) -> None:
    path = write_file(
        tmp_path / "src/example.py",
        '"""A human may set live_trading_enabled = 1 manually."""\n\nvalue = 0\n',
    )

    assert check_file(path) == []


def test_false_and_zero_are_allowed(tmp_path: Path) -> None:
    path = write_file(
        tmp_path / "tests/example.py",
        "row = {'live_trading_enabled': 0}\nbuild_account(live_trading_enabled=False)\nlive_trading_enabled = 0\n",
    )

    assert check_file(path) == []


def test_run_enforce_exit_one_with_findings(tmp_path: Path) -> None:
    write_file(tmp_path / "scripts/example.py", "row = {'live_trading_enabled': 1}\n")

    assert run_live_safety_check(tmp_path, enforce=True) == 1


def test_real_repo_live_safety_is_clean() -> None:
    repo_root = get_repo_root(Path(__file__))

    assert run_live_safety_check(repo_root, enforce=True) == 0
