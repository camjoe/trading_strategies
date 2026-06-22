from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from scripts.checks.link_check import (
    MD_LINK_RE,
    _check_backtick_path,
    _check_markdown_link,
    _is_external,
    _is_placeholder,
    check_file,
    discover_docs,
    run_link_check,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Regex / predicates
# ---------------------------------------------------------------------------


def test_md_link_re_captures_link_and_image_targets() -> None:
    assert MD_LINK_RE.findall("[Docs](maps/docs-map.md) and ![img](a.png)") == ["maps/docs-map.md", "a.png"]


def test_is_external() -> None:
    assert _is_external("https://example.com")
    assert _is_external("mailto:x@y.z")
    assert _is_external("#section")  # pure anchor
    assert not _is_external("maps/docs-map.md")


def test_is_placeholder() -> None:
    assert _is_placeholder("routes/<area>.py")
    assert not _is_placeholder("routes/accounts.py")


# ---------------------------------------------------------------------------
# Markdown link resolution (relative to the file)
# ---------------------------------------------------------------------------


def test_check_markdown_link_resolves_relative(tmp_path: Path) -> None:
    _write(tmp_path / "docs/a.md", "x")
    _write(tmp_path / "docs/sub/b.md", "x")
    doc_dir = tmp_path / "docs"
    assert _check_markdown_link("sub/b.md", doc_dir)
    assert _check_markdown_link("a.md#anchor", doc_dir)  # trailing anchor stripped
    assert _check_markdown_link("#top", doc_dir)  # pure anchor -> ok
    assert not _check_markdown_link("missing.md", doc_dir)


# ---------------------------------------------------------------------------
# Backtick repo-root path checks
# ---------------------------------------------------------------------------


def test_check_backtick_path(tmp_path: Path) -> None:
    _write(tmp_path / "docs/real.md", "x")
    assert _check_backtick_path("docs/real.md", tmp_path) is True
    assert _check_backtick_path("docs/missing.md", tmp_path) is False
    assert _check_backtick_path("EquitySnapshotRecord", tmp_path) is None  # not a repo path
    assert _check_backtick_path("trading/services/**/*.py", tmp_path) is None  # glob
    assert _check_backtick_path("trading/database/config.get_db_path()", tmp_path) is None  # function call
    assert _check_backtick_path("docs/real.md § Naming", tmp_path) is True  # section suffix ignored
    assert _check_backtick_path("docs/real.md::symbol", tmp_path) is True  # ::symbol suffix ignored


# ---------------------------------------------------------------------------
# check_file: flags broken refs, skips fenced code blocks
# ---------------------------------------------------------------------------


def test_check_file_flags_broken_and_skips_fences(tmp_path: Path) -> None:
    _write(tmp_path / "docs/exists.md", "x")
    doc = tmp_path / "docs/page.md"
    _write(
        doc,
        "[ok](exists.md)\n"
        "[bad](missing.md)\n"
        "`docs/exists.md` and `docs/missing.md`\n"
        "```\n"
        "[fenced](also-missing.md)\n"
        "```\n",
    )
    broken = {(ref.kind, ref.target) for ref in check_file(doc, tmp_path).broken}
    assert ("link", "missing.md") in broken
    assert ("path", "docs/missing.md") in broken
    assert ("link", "exists.md") not in broken  # resolves
    assert ("path", "docs/exists.md") not in broken  # resolves
    assert ("link", "also-missing.md") not in broken  # inside a fence -> skipped


def test_discover_docs_excludes_migration_and_agent_skills(tmp_path: Path) -> None:
    _write(tmp_path / "docs/keep.md", "x")
    _write(tmp_path / "docs-migration/plan.md", "x")
    _write(tmp_path / "docs/reference/agent-skills.md", "x")
    names = {path.name for path in discover_docs(tmp_path)}
    assert "keep.md" in names
    assert "plan.md" not in names  # docs-migration excluded
    assert "agent-skills.md" not in names  # upstream exception excluded


# ---------------------------------------------------------------------------
# Real repo (advisory) + CLI exit codes
# ---------------------------------------------------------------------------


def test_run_link_check_advisory_returns_zero_on_real_repo() -> None:
    """Advisory mode never fails the build, regardless of current broken references."""
    assert run_link_check(repo_root=PROJECT_ROOT) == 0


def test_cli_enforce_exits_nonzero_on_broken_link(tmp_path: Path) -> None:
    _write(tmp_path / "docs/page.md", "[bad](missing.md)\n")

    result = subprocess.run(
        [sys.executable, "-m", "scripts.checks.link_check", "--repo-root", str(tmp_path), "--enforce"],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "missing.md" in result.stdout
