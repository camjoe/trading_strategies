from __future__ import annotations

import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _run_check(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "scripts.checks.readme_check", "--repo-root", str(repo), *args],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )


def test_readme_consistency_warns_but_passes_by_default(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("not a heading\n", encoding="utf-8")

    result = _run_check(repo)

    assert result.returncode == 0
    assert "WARN: README consistency audit found advisory issues." in result.stdout


def test_readme_consistency_fails_with_enforce_style(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("not a heading\n", encoding="utf-8")

    result = _run_check(repo, "--enforce-style")

    assert result.returncode == 1
    assert "FAIL: README consistency audit failed in enforce mode." in result.stdout


def test_readme_consistency_flags_stale_readmes(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Title\n\n## Project Overview\n", encoding="utf-8")

    result = _run_check(repo, "--max-age-days", "0")

    assert result.returncode == 0
    assert "Stale README files: 0 (threshold days: 0)" in result.stdout


def test_readme_consistency_ignores_code_fence_headings(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text(
        "\n".join(
            [
                "# Repo",
                "",
                "## Project Overview",
                "",
                "```markdown",
                "# Not a real heading",
                "## Also not real",
                "```",
                "",
                "## Directory Structure",
                "## Quick Start",
                "## Testing",
                "## Documentation Index",
            ]
        ),
        encoding="utf-8",
    )

    result = _run_check(repo, "--enforce-style")

    assert result.returncode == 0
    assert "Style issues: 0" in result.stdout
