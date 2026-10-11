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


def test_remove_and_commit_deletes_and_updates_in_one_commit(repo: Path) -> None:
    (repo / "gone.md").write_text("x", encoding="utf-8")
    git(repo, "add", "gone.md")
    git(repo, "commit", "-q", "-m", "add gone")
    (repo / "a.txt").write_text("changed", encoding="utf-8")

    LocalGit(repo).remove_and_commit([repo / "gone.md"], [repo / "a.txt"], "remove gone")

    assert not (repo / "gone.md").exists()
    assert git(repo, "log", "-1", "--format=%s") == "remove gone"
    assert sorted(git(repo, "show", "--name-only", "--format=", "HEAD").splitlines()) == ["a.txt", "gone.md"]
    assert git(repo, "status", "--porcelain") == ""


def test_a_renamed_file_is_reported_as_both_its_old_and_new_path(repo: Path) -> None:
    (repo / "guarded").mkdir()
    (repo / "guarded" / "a.py").write_text("x", encoding="utf-8")
    git(repo, "add", "guarded")
    git(repo, "commit", "-q", "-m", "add guarded")
    local = LocalGit(repo)
    start = local.head()
    git(repo, "mv", "guarded/a.py", "elsewhere.py")
    git(repo, "commit", "-q", "-m", "move it out")

    assert sorted(local.changed_paths(start, local.head())) == ["elsewhere.py", "guarded/a.py"]


def test_dirty_paths_lists_modified_and_untracked_files_and_nothing_when_clean(repo: Path) -> None:
    local = LocalGit(repo)
    assert local.dirty_paths() == []
    (repo / "a.txt").write_text("changed", encoding="utf-8")
    (repo / "new.txt").write_text("n", encoding="utf-8")

    assert sorted(local.dirty_paths()) == ["a.txt", "new.txt"]


def test_discard_changes_drops_later_commits_edits_and_untracked_files(repo: Path) -> None:
    local = LocalGit(repo)
    start = local.head()
    (repo / "c.txt").write_text("c", encoding="utf-8")
    local.commit_files([repo / "c.txt"], "add c")
    (repo / "a.txt").write_text("edited", encoding="utf-8")
    (repo / "stray.txt").write_text("s", encoding="utf-8")

    local.discard_changes(start)

    assert local.head() == start and local.dirty_paths() == []
    assert not (repo / "c.txt").exists() and not (repo / "stray.txt").exists()


def test_push_sends_head_to_the_named_branch_whatever_the_upstream_is(repo: Path, tmp_path: Path) -> None:
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(remote))
    git(repo, "remote", "add", "origin", str(remote))
    git(repo, "switch", "-q", "-c", "local-name")

    LocalGit(repo).push("pr-head")

    assert git(remote, "rev-parse", "--verify", "refs/heads/pr-head") == git(repo, "rev-parse", "HEAD")
    assert subprocess.run(["git", "rev-parse", "--verify", "refs/heads/local-name"], cwd=remote).returncode != 0


def test_a_failed_push_is_a_forge_error(repo: Path) -> None:
    git(repo, "remote", "add", "origin", str(repo / "no-such-remote"))

    with pytest.raises(ForgeError, match="git push to pr-head failed"):
        LocalGit(repo).push("pr-head")
