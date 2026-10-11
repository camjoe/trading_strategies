import subprocess
from pathlib import Path

import pytest

from scripts.forge.base import ForgeError
from scripts.forge.local import LocalGit


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q", "-b", "develop")
    git(tmp_path, "config", "user.email", "t@example.test")
    git(tmp_path, "config", "user.name", "t")
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    git(tmp_path, "add", "a.txt")
    git(tmp_path, "commit", "-q", "-m", "first")
    return tmp_path


def test_create_branch_switches_to_a_new_branch_from_the_start_point(repo: Path) -> None:
    LocalGit(repo).create_branch("feature/x", "develop")

    assert git(repo, "branch", "--show-current") == "feature/x"


def test_creating_an_existing_branch_is_a_forge_error(repo: Path) -> None:
    git(repo, "branch", "feature/x")

    with pytest.raises(ForgeError, match="Could not create branch"):
        LocalGit(repo).create_branch("feature/x", "develop")


def test_commit_files_commits_only_the_named_files(repo: Path) -> None:
    (repo / "b.txt").write_text("b", encoding="utf-8")
    (repo / "other.txt").write_text("o", encoding="utf-8")

    LocalGit(repo).commit_files([repo / "b.txt"], "add b")

    assert git(repo, "log", "-1", "--format=%s") == "add b"
    assert git(repo, "show", "--name-only", "--format=", "HEAD") == "b.txt"


def test_a_dirty_tree_is_refused_and_a_clean_one_passes(repo: Path) -> None:
    local = LocalGit(repo)
    local.require_clean_tree()
    (repo / "a.txt").write_text("changed", encoding="utf-8")

    with pytest.raises(ForgeError, match="uncommitted"):
        local.require_clean_tree()


def test_head_and_changed_paths_follow_new_commits(repo: Path) -> None:
    local = LocalGit(repo)
    start = local.head()
    (repo / "c.txt").write_text("c", encoding="utf-8")
    local.commit_files([repo / "c.txt"], "add c")

    assert local.head() != start
    assert local.changed_paths(start, local.head()) == ["c.txt"]
