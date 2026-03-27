from __future__ import annotations

from pathlib import Path

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
