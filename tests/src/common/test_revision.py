"""git_head_revision is best-effort: a SHA when git resolves, None otherwise."""

from __future__ import annotations

from pathlib import Path

import pytest

from common import revision


def _fixed_repo_root(_start: object) -> Path:
    return Path("/repo")


def test_returns_sha_when_git_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    revision.git_head_revision.cache_clear()
    monkeypatch.setattr(revision, "get_repo_root", _fixed_repo_root)
    monkeypatch.setattr(revision, "run_git", lambda *_a, **_k: "deadbeef")

    assert revision.git_head_revision() == "deadbeef"
    revision.git_head_revision.cache_clear()


def test_returns_none_when_git_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    revision.git_head_revision.cache_clear()
    monkeypatch.setattr(revision, "get_repo_root", _fixed_repo_root)
    monkeypatch.setattr(revision, "run_git", lambda *_a, **_k: None)

    assert revision.git_head_revision() is None
    revision.git_head_revision.cache_clear()


def test_asks_git_for_head_in_the_repo_root(monkeypatch: pytest.MonkeyPatch) -> None:
    revision.git_head_revision.cache_clear()
    seen: list[tuple[tuple[str, ...], str]] = []

    def _fake_run_git(*args: str, cwd: str) -> str:
        seen.append((args, cwd))
        return "deadbeef"

    monkeypatch.setattr(revision, "get_repo_root", _fixed_repo_root)
    monkeypatch.setattr(revision, "run_git", _fake_run_git)

    revision.git_head_revision()

    assert seen == [(("rev-parse", "HEAD"), str(Path("/repo")))]
    revision.git_head_revision.cache_clear()


def test_returns_none_when_repo_root_unresolved(monkeypatch: pytest.MonkeyPatch) -> None:
    revision.git_head_revision.cache_clear()

    def _raise(_start: object) -> object:
        raise RuntimeError("no repo root")

    monkeypatch.setattr(revision, "get_repo_root", _raise)

    assert revision.git_head_revision() is None
    revision.git_head_revision.cache_clear()
