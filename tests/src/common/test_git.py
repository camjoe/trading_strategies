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
