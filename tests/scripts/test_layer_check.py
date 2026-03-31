from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from scripts.checks.layer_check import LayerRule, check_rule, run_layer_check


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _run_script(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "scripts.checks.layer_check", "--repo-root", str(repo)],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )


# ---------------------------------------------------------------------------
# Integration test — real repo must be clean
# ---------------------------------------------------------------------------

def test_layer_check_passes_on_real_repo() -> None:
    """The actual codebase must have zero layer violations."""
    result = run_layer_check(repo_root=PROJECT_ROOT)
    assert result == 0


# ---------------------------------------------------------------------------
# Unit tests for check_rule logic
# ---------------------------------------------------------------------------

def _write_py(directory: Path, name: str, source: str) -> Path:
    path = directory / name
    path.write_text(source, encoding="utf-8")
    return path


def test_check_rule_detects_forbidden_import(tmp_path: Path) -> None:
    src = tmp_path / "services"
    src.mkdir()
    _write_py(src, "bad.py", "from trading.database.db import ensure_db\n")

    rule = LayerRule(
        label="test-rule",
        source_glob="services/**/*.py",
        forbidden_prefixes=("trading.database.",),
    )
    violations = check_rule(tmp_path, rule)
    assert len(violations) == 1
    assert violations[0].import_text == "trading.database.db"
    assert violations[0].rule_label == "test-rule"


def test_check_rule_allows_non_forbidden_import(tmp_path: Path) -> None:
    src = tmp_path / "services"
    src.mkdir()
    _write_py(src, "ok.py", "from trading.repositories.accounts import fetch_accounts\n")

    rule = LayerRule(
        label="test-rule",
        source_glob="services/**/*.py",
        forbidden_prefixes=("trading.database.",),
    )
    violations = check_rule(tmp_path, rule)
    assert violations == []


def test_check_rule_honours_exceptions(tmp_path: Path) -> None:
    src = tmp_path / "services"
    src.mkdir()
    _write_py(src, "db.py", "from trading.database.db import ensure_db\n")

    rule = LayerRule(
        label="test-rule",
        source_glob="services/**/*.py",
        forbidden_prefixes=("trading.database.",),
        exceptions=("services/db.py",),
    )
    violations = check_rule(tmp_path, rule)
    assert violations == []


def test_check_rule_skips_syntax_errors_gracefully(tmp_path: Path) -> None:
    src = tmp_path / "services"
    src.mkdir()
    _write_py(src, "broken.py", "def (:\n")

    rule = LayerRule(
        label="test-rule",
        source_glob="services/**/*.py",
        forbidden_prefixes=("trading.database.",),
    )
    violations = check_rule(tmp_path, rule)
    assert violations == []


# ---------------------------------------------------------------------------
# CLI exit-code tests
# ---------------------------------------------------------------------------

def test_cli_exits_zero_when_no_violations(tmp_path: Path) -> None:
    src = tmp_path / "services"
    src.mkdir()
    _write_py(src, "clean.py", "import os\n")

    rule_glob_dir = tmp_path / "paper_trading_ui" / "backend" / "services"
    rule_glob_dir.mkdir(parents=True)

    result = _run_script(tmp_path)
    assert result.returncode == 0
    assert "passed" in result.stdout


def test_cli_exits_one_when_violations_present(tmp_path: Path) -> None:
    bad_dir = tmp_path / "paper_trading_ui" / "backend" / "routes"
    bad_dir.mkdir(parents=True)
    _write_py(bad_dir, "bad.py", "from trading.database.db import ensure_db\n")

    result = _run_script(tmp_path)
    assert result.returncode == 1
    assert "FAILED" in result.stdout
