"""Tests for scripts.checks.repo.skills_check."""

from __future__ import annotations

from pathlib import Path

from common.paths.repo_paths import get_repo_root
from scripts.checks.repo.skills_check import (
    frontmatter_problems,
    run_skills_check,
    skills_in_inventory,
    skills_on_disk,
)

VALID_SKILL = "---\nname: demo-skill\ndescription: Does X. Use when Y.\ninvoker: any\n---\n\n# Demo\n"


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _agents_md(tmp_path: Path, skills: list[str], routing_rows: str = "") -> None:
    inventory = "\n".join(f"| `{name}/` | Some purpose |" for name in skills)
    _write(
        tmp_path / "AGENTS.md",
        "# Guide\n\nCurrent skill inventory:\n\n| Skill | Purpose |\n|---|---|\n"
        f"{inventory}\n\n## Routing guide\n\n| Task shape | Preferred surface |\n|---|---|\n"
        f"{routing_rows}\n",
    )


def test_in_sync_passes(tmp_path: Path) -> None:
    _write(tmp_path / ".ai/skills/demo-skill/SKILL.md", VALID_SKILL)
    _agents_md(tmp_path, ["demo-skill"])
    assert run_skills_check(tmp_path, enforce=True) == 0


def test_routing_table_rows_do_not_count_as_inventory(tmp_path: Path) -> None:
    _write(tmp_path / ".ai/skills/demo-skill/SKILL.md", VALID_SKILL)
    # Routing row references another skill in its second cell — must not satisfy the inventory.
    _agents_md(tmp_path, ["demo-skill"], routing_rows="| Review a diff | `other-skill/` (Standard) |")
    assert skills_in_inventory(tmp_path) == {"demo-skill"}


def test_skill_on_disk_missing_from_inventory(tmp_path: Path, capsys) -> None:
    _write(tmp_path / ".ai/skills/demo-skill/SKILL.md", VALID_SKILL)
    _write(tmp_path / ".ai/skills/orphan/SKILL.md", VALID_SKILL)
    _agents_md(tmp_path, ["demo-skill"])
    assert run_skills_check(tmp_path, enforce=True) == 1
    assert "orphan" in capsys.readouterr().out


def test_inventory_row_missing_from_disk(tmp_path: Path, capsys) -> None:
    _write(tmp_path / ".ai/skills/demo-skill/SKILL.md", VALID_SKILL)
    _agents_md(tmp_path, ["demo-skill", "ghost"])
    assert run_skills_check(tmp_path, enforce=True) == 1
    assert "ghost" in capsys.readouterr().out


def test_frontmatter_problems_variants(tmp_path: Path) -> None:
    no_block = _write(tmp_path / "a/SKILL.md", "# No frontmatter\n")
    assert frontmatter_problems(no_block) == ["missing frontmatter block"]

    unterminated = _write(tmp_path / "b/SKILL.md", "---\nname: x\ndescription: y\ninvoker: any\n")
    assert frontmatter_problems(unterminated) == ["unterminated frontmatter block"]

    incomplete = _write(tmp_path / "c/SKILL.md", "---\nname: x\n---\n")
    problems = frontmatter_problems(incomplete)
    assert "missing frontmatter field: description" in problems
    assert "missing frontmatter field: invoker" in problems

    bad_invoker = _write(tmp_path / "d/SKILL.md", "---\nname: x\ndescription: y\ninvoker: agent:retired\n---\n")
    assert any("invalid invoker" in p for p in frontmatter_problems(bad_invoker))


def test_advisory_mode_exits_zero_with_findings(tmp_path: Path) -> None:
    _write(tmp_path / ".ai/skills/orphan/SKILL.md", VALID_SKILL)
    _agents_md(tmp_path, [])
    assert run_skills_check(tmp_path) == 0


def test_real_repo_skills_are_in_sync() -> None:
    repo_root = get_repo_root(Path(__file__))
    assert skills_on_disk(repo_root)  # sanity: the repo has skills
    assert run_skills_check(repo_root, enforce=True) == 0
