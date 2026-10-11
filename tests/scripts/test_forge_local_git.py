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


def test_discard_changes_drops_later_commits_edits_and_untracked_files(repo: Path) -> None:
    local = LocalGit(repo)
    start = local.head()
    (repo / "c.txt").write_text("c", encoding="utf-8")
    local.commit_files([repo / "c.txt"], "add c")
    (repo / "a.txt").write_text("edited", encoding="utf-8")
    (repo / "stray.txt").write_text("s", encoding="utf-8")

    local.discard_changes(start)

    assert local.head() == start and git(repo, "status", "--porcelain") == ""
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


def test_a_failed_claim_can_be_retried_after_the_cleanup_the_pickup_does(repo: Path) -> None:
    local = LocalGit(repo)
    local.create_branch("feature/x", "develop")
    fresh = local.head()
    (repo / "plan.md").write_text("claimed", encoding="utf-8")
    local.commit_files([repo / "plan.md"], "claim")

    local.discard_changes(fresh)
    local.switch("develop")
    local.delete_branch("feature/x")

    local.require_clean_tree()
    local.create_branch("feature/x", "develop")
    assert local.current_branch() == "feature/x"


def test_discarding_changes_does_not_touch_ignored_files(repo: Path) -> None:
    (repo / ".gitignore").write_text("secret.txt\n", encoding="utf-8")
    git(repo, "add", ".gitignore")
    git(repo, "commit", "-q", "-m", "ignore")
    local = LocalGit(repo)
    (repo / "secret.txt").write_text("planted", encoding="utf-8")

    local.discard_changes(local.head())

    assert (repo / "secret.txt").read_text(encoding="utf-8") == "planted"


def test_import_commits_fetches_a_clones_head_without_touching_the_checkout(repo: Path, tmp_path: Path) -> None:
    clone = tmp_path / "clone"
    git(tmp_path, "clone", "-q", str(repo), str(clone))
    git(clone, "config", "user.name", "t")
    git(clone, "config", "user.email", "t@t")
    (clone / "new.txt").write_text("n", encoding="utf-8")
    git(clone, "add", "new.txt")
    git(clone, "commit", "-q", "-m", "in the clone")
    local = LocalGit(repo)
    before = local.head()

    imported = local.import_commits(clone, before)

    assert imported == git(clone, "rev-parse", "HEAD") and local.head() == before
    assert not (repo / "new.txt").exists()
    assert local.changed_paths(before, imported) == ["new.txt"]


def test_fast_forward_applies_imported_commits_and_refuses_ones_that_do_not_descend(
    repo: Path, tmp_path: Path
) -> None:
    clone = tmp_path / "clone"
    git(tmp_path, "clone", "-q", str(repo), str(clone))
    git(clone, "config", "user.name", "t")
    git(clone, "config", "user.email", "t@t")
    (clone / "new.txt").write_text("n", encoding="utf-8")
    git(clone, "add", "new.txt")
    git(clone, "commit", "-q", "-m", "in the clone")
    local = LocalGit(repo)
    first = local.head()
    imported = local.import_commits(clone, first)

    local.fast_forward(imported)

    assert local.head() == imported and (repo / "new.txt").exists()

    (repo / "diverge.txt").write_text("d", encoding="utf-8")
    git(repo, "add", "diverge.txt")
    git(repo, "commit", "-q", "-m", "diverge")
    git(clone, "reset", "-q", "--hard", "HEAD~1")
    (clone / "other.txt").write_text("o", encoding="utf-8")
    git(clone, "add", "other.txt")
    git(clone, "commit", "-q", "-m", "elsewhere")
    elsewhere = local.import_commits(clone, first)

    with pytest.raises(ForgeError, match="merge failed"):
        local.fast_forward(elsewhere)


def test_hold_keeps_a_commit_under_a_local_only_ref(repo: Path) -> None:
    sha = git(repo, "rev-parse", "HEAD")

    ref = LocalGit(repo).hold("plan/x", sha)

    assert ref == "refs/forge/held/plan/x" and git(repo, "rev-parse", ref) == sha
    assert git(repo, "for-each-ref", "refs/heads", "refs/remotes") == git(repo, "for-each-ref", "refs/heads")


def test_a_hook_planted_in_the_checkout_does_not_run_when_the_controller_merges(repo: Path, tmp_path: Path) -> None:
    clone = tmp_path.parent / (tmp_path.name + "-clone")
    git(tmp_path, "clone", "-q", str(repo), str(clone))
    git(clone, "config", "user.name", "t")
    git(clone, "config", "user.email", "t@t")
    (clone / "new.txt").write_text("n", encoding="utf-8")
    git(clone, "add", "new.txt")
    git(clone, "commit", "-q", "-m", "change")
    local = LocalGit(repo)
    imported = local.import_commits(clone, local.head())
    marker = repo / "hook-ran.txt"
    hook = repo / ".git" / "hooks" / "post-merge"
    hook.parent.mkdir(exist_ok=True)
    hook.write_text(f"#!/bin/sh\necho ran > '{marker.as_posix()}'\n", encoding="utf-8", newline="\n")
    hook.chmod(0o755)

    local.fast_forward(imported)

    assert (repo / "new.txt").exists() and not marker.exists()
