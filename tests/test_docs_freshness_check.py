from __future__ import annotations

import subprocess
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "check_docs_freshness.py"


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, check=False)


def _run_docs_check(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return _run([sys.executable, str(SCRIPT_PATH), "--repo-root", str(repo), *args], repo)


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(["git", "init"], repo)
    _run(["git", "config", "user.email", "tests@example.com"], repo)
    _run(["git", "config", "user.name", "Tests"], repo)

    (repo / "README.md").write_text("# temp repo\n", encoding="utf-8")
    (repo / "trading").mkdir()
    (repo / "trading" / "module.py").write_text("print('v1')\n", encoding="utf-8")

    _run(["git", "add", "."], repo)
    _run(["git", "commit", "-m", "initial"], repo)
    return repo


def test_docs_freshness_fails_for_code_change_without_docs(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    (repo / "trading" / "module.py").write_text("print('v2')\n", encoding="utf-8")

    result = _run_docs_check(repo)

    assert result.returncode == 1
    assert "FAIL: Documentation is stale" in result.stdout
    assert "- trading" in result.stdout


def test_docs_freshness_passes_with_matching_readme_update(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    (repo / "trading" / "module.py").write_text("print('v2')\n", encoding="utf-8")
    (repo / "trading" / "README.md").write_text("# trading docs\n", encoding="utf-8")

    result = _run_docs_check(repo)

    assert result.returncode == 0
    assert "PASS: Documentation freshness check passed." in result.stdout


def test_docs_freshness_supports_base_ref_diff(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    (repo / "trading" / "module.py").write_text("print('v2')\n", encoding="utf-8")
    _run(["git", "add", "."], repo)
    _run(["git", "commit", "-m", "code change"], repo)

    result = _run_docs_check(repo, "--base-ref", "HEAD~1", "--head-ref", "HEAD")

    assert result.returncode == 1
    assert "Change source: HEAD~1...HEAD" in result.stdout