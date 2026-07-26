"""git_head_revision is best-effort: a SHA when git resolves, None otherwise."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from common import revision


def _fixed_repo_root(_start: object) -> Path:
    return Path("/repo")


def test_returns_sha_when_git_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    revision.git_head_revision.cache_clear()
    monkeypatch.setattr(revision, "get_repo_root", _fixed_repo_root)
    monkeypatch.setattr(
        revision.subprocess,
        "run",
        lambda *_a, **_k: subprocess.CompletedProcess(args=[], returncode=0, stdout="deadbeef\n", stderr=""),
    )

    assert revision.git_head_revision() == "deadbeef"
    revision.git_head_revision.cache_clear()


def test_returns_none_when_git_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    revision.git_head_revision.cache_clear()
    monkeypatch.setattr(revision, "get_repo_root", _fixed_repo_root)
    monkeypatch.setattr(
        revision.subprocess,
        "run",
        lambda *_a, **_k: subprocess.CompletedProcess(args=[], returncode=128, stdout="", stderr="not a repo"),
    )

    assert revision.git_head_revision() is None
    revision.git_head_revision.cache_clear()


def test_returns_none_when_repo_root_unresolved(monkeypatch: pytest.MonkeyPatch) -> None:
    revision.git_head_revision.cache_clear()

    def _raise(_start: object) -> object:
        raise RuntimeError("no repo root")

    monkeypatch.setattr(revision, "get_repo_root", _raise)

    assert revision.git_head_revision() is None
    revision.git_head_revision.cache_clear()
