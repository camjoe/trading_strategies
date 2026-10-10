"""Git interrogation of the checkout: run_git, get_repo_root, git_head_revision.

Layered deliberately — `run_git` is tested against a fake `subprocess.run`, and
the two callers above it are tested against a fake `run_git`, so the subprocess
contract is asserted in exactly one place.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from common import git
from common.git import _discover_repo_root_via_git, get_repo_root


@pytest.fixture(autouse=True)
def _clear_caches() -> None:
    _discover_repo_root_via_git.cache_clear()
    git.git_head_revision.cache_clear()


def _completed(returncode: int, stdout: str) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")


def _fixed_repo_root(_start: object) -> Path:
    return Path("/repo")


class TestRunGit:
    def test_returns_stripped_stdout_when_git_succeeds(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(git.subprocess, "run", lambda *_a, **_k: _completed(0, "deadbeef\n"))

        assert git.run_git("rev-parse", "HEAD", cwd=".") == "deadbeef"

    def test_returns_none_when_git_exits_non_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(git.subprocess, "run", lambda *_a, **_k: _completed(128, ""))

        assert git.run_git("rev-parse", "HEAD", cwd=".") is None

    def test_returns_none_when_output_is_blank(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(git.subprocess, "run", lambda *_a, **_k: _completed(0, "\n"))

        assert git.run_git("rev-parse", "--show-toplevel", cwd=".") is None

    def test_passes_cwd_and_args_through_to_git(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seen: list[list[str]] = []

        def _fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            seen.append(command)
            return _completed(0, "ok")

        monkeypatch.setattr(git.subprocess, "run", _fake_run)

        git.run_git("rev-parse", "HEAD", cwd="/repo")

        assert seen == [["git", "-C", "/repo", "rev-parse", "HEAD"]]


class TestGetRepoRoot:
    def test_raises_when_git_cannot_resolve_a_root(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        nested = tmp_path / "repo" / "a" / "b"
        nested.mkdir(parents=True)
        monkeypatch.setattr(git, "_discover_repo_root_via_git", lambda _start_dir: None)

        with pytest.raises(RuntimeError, match="Unable to determine repository root via git"):
            get_repo_root(nested)

    def test_git_top_level_used_when_available(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        project = tmp_path / "project"
        project.mkdir(parents=True)
        monkeypatch.setattr(git, "_discover_repo_root_via_git", lambda _start_dir: project.resolve())

        assert get_repo_root(project) == project.resolve()

    def test_uses_parent_when_start_is_file(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        project = tmp_path / "project"
        nested = project / "src"
        nested.mkdir(parents=True)
        file_path = nested / "module.py"
        file_path.write_text("# marker\n", encoding="utf-8")

        seen: list[str] = []

        def _fake_discover(start_dir: str) -> Path:
            seen.append(start_dir)
            return project.resolve()

        monkeypatch.setattr(git, "_discover_repo_root_via_git", _fake_discover)

        assert get_repo_root(file_path) == project.resolve()
        assert seen == [str(nested.resolve())]

    def test_uses_cwd_when_start_is_none(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        cwd = tmp_path / "workspace"
        cwd.mkdir(parents=True)
        monkeypatch.chdir(cwd)

        seen: list[str] = []

        def _fake_discover(start_dir: str) -> Path:
            seen.append(start_dir)
            return cwd.resolve()

        monkeypatch.setattr(git, "_discover_repo_root_via_git", _fake_discover)

        assert get_repo_root() == cwd.resolve()
        assert seen == [str(cwd.resolve())]


class TestDiscoverRepoRootViaGit:
    """Patches the ``run_git`` seam; ``run_git``'s own failure modes live in TestRunGit."""

    def test_returns_none_when_git_cannot_resolve_a_root(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(git, "run_git", lambda *_args, **_kwargs: None)

        assert _discover_repo_root_via_git(".") is None

    def test_returns_none_when_git_path_is_not_directory(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        file_path = tmp_path / "not_a_dir.txt"
        file_path.write_text("x", encoding="utf-8")
        monkeypatch.setattr(git, "run_git", lambda *_args, **_kwargs: str(file_path))

        assert _discover_repo_root_via_git(".") is None

    def test_returns_resolved_directory_when_git_succeeds(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        project = tmp_path / "project"
        project.mkdir(parents=True)
        monkeypatch.setattr(git, "run_git", lambda *_args, **_kwargs: str(project))

        assert _discover_repo_root_via_git(".") == project.resolve()

    def test_asks_git_for_the_top_level_of_the_start_directory(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seen: list[tuple[tuple[str, ...], str]] = []

        def _fake_run_git(*args: str, cwd: str) -> None:
            seen.append((args, cwd))
            return None

        monkeypatch.setattr(git, "run_git", _fake_run_git)

        _discover_repo_root_via_git("/some/dir")

        assert seen == [(("rev-parse", "--show-toplevel"), "/some/dir")]

    def test_is_cached_for_same_start_directory(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        project = tmp_path / "project"
        project.mkdir(parents=True)
        calls = {"count": 0}

        def _fake_run_git(*_args: str, **_kwargs: object) -> str:
            calls["count"] += 1
            return str(project)

        monkeypatch.setattr(git, "run_git", _fake_run_git)

        first = _discover_repo_root_via_git(str(project))
        second = _discover_repo_root_via_git(str(project))

        assert first == project.resolve()
        assert second == project.resolve()
        assert calls["count"] == 1


class TestGitHeadRevision:
    """Best-effort: a SHA when git resolves, None otherwise."""

    def test_returns_sha_when_git_succeeds(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(git, "get_repo_root", _fixed_repo_root)
        monkeypatch.setattr(git, "run_git", lambda *_a, **_k: "deadbeef")

        assert git.git_head_revision() == "deadbeef"

    def test_returns_none_when_git_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(git, "get_repo_root", _fixed_repo_root)
        monkeypatch.setattr(git, "run_git", lambda *_a, **_k: None)

        assert git.git_head_revision() is None

    def test_returns_none_when_repo_root_unresolved(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _raise(_start: object) -> object:
            raise RuntimeError("no repo root")

        monkeypatch.setattr(git, "get_repo_root", _raise)

        assert git.git_head_revision() is None

    def test_asks_git_for_head_in_the_repo_root(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seen: list[tuple[tuple[str, ...], str]] = []

        def _fake_run_git(*args: str, cwd: str) -> str:
            seen.append((args, cwd))
            return "deadbeef"

        monkeypatch.setattr(git, "get_repo_root", _fixed_repo_root)
        monkeypatch.setattr(git, "run_git", _fake_run_git)

        git.git_head_revision()

        assert seen == [(("rev-parse", "HEAD"), str(Path("/repo")))]


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@example.test", "-c", "user.name=t", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(tmp_path, "init", "-b", "main", str(repo))
    (repo / "old.py").write_text("x = 1\n" * 40, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "base")
    return repo


class TestStrictHelpers:
    def test_git_output_returns_stdout(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)

        assert git.git_output(repo, "log", "--format=%s") == "base\n"

    def test_git_output_raises_when_git_fails(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)

        with pytest.raises(subprocess.CalledProcessError) as raised:
            git.git_output(repo, "rev-parse", "no-such-ref")

        assert raised.value.returncode != 0
        assert "no-such-ref" in " ".join(raised.value.cmd)

    def test_split_nul_drops_empty_entries(self) -> None:
        assert git.split_nul("a.py\0b c.py\0") == ["a.py", "b c.py"]
        assert git.split_nul("") == []

    def test_diff_range_is_three_dot_with_a_base_and_head_without(self) -> None:
        assert git.diff_range("develop") == ["develop...HEAD"]
        assert git.diff_range("develop", "feature") == ["develop...feature"]
        assert git.diff_range(None) == ["HEAD"]

    def test_changed_paths_returns_unquoted_names_for_branch_changes(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        _git(repo, "checkout", "-b", "feature")
        (repo / "módulo.py").write_text("y = 2\n", encoding="utf-8")
        (repo / "has space.py").write_text("z = 3\n", encoding="utf-8")
        _git(repo, "mv", "old.py", "new.py")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-m", "change")

        assert sorted(git.changed_paths(repo, "main")) == ["has space.py", "módulo.py", "new.py"]

    def test_changed_paths_reads_a_ref_that_is_not_checked_out(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        _git(repo, "checkout", "-b", "feature")
        (repo / "added.py").write_text("y = 2\n", encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-m", "change")
        _git(repo, "checkout", "main")

        assert git.changed_paths(repo, "main", "feature") == ["added.py"]

    def test_changed_paths_without_a_base_diffs_the_working_tree_against_head(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        (repo / "old.py").write_text("x = 2\n", encoding="utf-8")

        assert git.changed_paths(repo) == ["old.py"]

    def test_untracked_paths_lists_files_git_does_not_ignore(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        (repo / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
        _git(repo, "add", ".gitignore")
        (repo / "ignored.txt").write_text("i\n", encoding="utf-8")
        (repo / "módulo.py").write_text("y = 2\n", encoding="utf-8")

        assert git.untracked_paths(repo) == ["módulo.py"]

    def test_uncommitted_paths_returns_plain_paths_for_renames_spaces_and_non_ascii_names(
        self, tmp_path: Path
    ) -> None:
        repo = _repo(tmp_path)
        assert git.uncommitted_paths(repo) == []

        _git(repo, "mv", "old.py", "new.py")
        (repo / "has space.py").write_text("z = 3\n", encoding="utf-8")
        (repo / "módulo.py").write_text("y = 2\n", encoding="utf-8")

        assert sorted(git.uncommitted_paths(repo)) == ["has space.py", "módulo.py", "new.py"]

    def test_resolve_ref_returns_the_abbreviated_commit(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        head = git.git_output(repo, "rev-parse", "HEAD").strip()

        assert head.startswith(git.resolve_ref(repo, "main"))
        assert 4 <= len(git.resolve_ref(repo, "main")) < len(head)
