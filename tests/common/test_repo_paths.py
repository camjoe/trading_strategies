from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

import common.repo_paths as repo_paths
from common.repo_paths import _discover_repo_root_via_git, get_repo_root


@pytest.fixture(autouse=True)
def _clear_repo_root_cache() -> None:
    _discover_repo_root_via_git.cache_clear()


def test_git_missing_raises_runtime_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    nested = tmp_path / "repo" / "a" / "b"
    nested.mkdir(parents=True)
    monkeypatch.setattr(repo_paths, "_discover_repo_root_via_git", lambda _start_dir: None)

    with pytest.raises(RuntimeError, match="Unable to determine repository root via git"):
        get_repo_root(nested)


def test_git_top_level_used_when_available(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir(parents=True)
    monkeypatch.setattr(repo_paths, "_discover_repo_root_via_git", lambda _start_dir: project.resolve())

    resolved = get_repo_root(project)

    assert resolved == project.resolve()


def test_get_repo_root_uses_parent_when_start_is_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    project = tmp_path / "project"
    nested = project / "src"
    nested.mkdir(parents=True)
    file_path = nested / "module.py"
    file_path.write_text("# marker\n", encoding="utf-8")

    seen: list[str] = []

    def _fake_discover(start_dir: str) -> Path:
        seen.append(start_dir)
        return project.resolve()

    monkeypatch.setattr(repo_paths, "_discover_repo_root_via_git", _fake_discover)

    resolved = get_repo_root(file_path)

    assert resolved == project.resolve()
    assert seen == [str(nested.resolve())]


def test_get_repo_root_uses_cwd_when_start_is_none(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cwd = tmp_path / "workspace"
    cwd.mkdir(parents=True)
    monkeypatch.chdir(cwd)

    seen: list[str] = []

    def _fake_discover(start_dir: str) -> Path:
        seen.append(start_dir)
        return cwd.resolve()

    monkeypatch.setattr(repo_paths, "_discover_repo_root_via_git", _fake_discover)

    resolved = get_repo_root()

    assert resolved == cwd.resolve()
    assert seen == [str(cwd.resolve())]


class TestDiscoverRepoRootViaGit:
    def test_returns_none_when_git_command_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            repo_paths.subprocess,
            "run",
            lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout="", stderr="fatal"),
        )

        assert _discover_repo_root_via_git(".") is None

    def test_returns_none_when_git_output_is_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            repo_paths.subprocess,
            "run",
            lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="\n", stderr=""),
        )

        assert _discover_repo_root_via_git(".") is None

    def test_returns_none_when_git_path_is_not_directory(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        file_path = tmp_path / "not_a_dir.txt"
        file_path.write_text("x", encoding="utf-8")
        monkeypatch.setattr(
            repo_paths.subprocess,
            "run",
            lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=str(file_path), stderr=""),
        )

        assert _discover_repo_root_via_git(".") is None

    def test_returns_resolved_directory_when_git_succeeds(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        project = tmp_path / "project"
        project.mkdir(parents=True)
        monkeypatch.setattr(
            repo_paths.subprocess,
            "run",
            lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=str(project), stderr=""),
        )

        assert _discover_repo_root_via_git(".") == project.resolve()

    def test_is_cached_for_same_start_directory(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        project = tmp_path / "project"
        project.mkdir(parents=True)
        calls = {"count": 0}

        def _fake_run(*_args, **_kwargs) -> subprocess.CompletedProcess[str]:
            calls["count"] += 1
            return SimpleNamespace(returncode=0, stdout=str(project), stderr="")

        monkeypatch.setattr(repo_paths.subprocess, "run", _fake_run)

        first = _discover_repo_root_via_git(str(project))
        second = _discover_repo_root_via_git(str(project))

        assert first == project.resolve()
        assert second == project.resolve()
        assert calls["count"] == 1
