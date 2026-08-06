"""run_git is best-effort: stripped stdout when git succeeds, None otherwise."""

from __future__ import annotations

import subprocess

import pytest

from common import git


def _completed(returncode: int, stdout: str) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")


def test_returns_stripped_stdout_when_git_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(git.subprocess, "run", lambda *_a, **_k: _completed(0, "deadbeef\n"))

    assert git.run_git("rev-parse", "HEAD", cwd=".") == "deadbeef"


def test_returns_none_when_git_exits_non_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(git.subprocess, "run", lambda *_a, **_k: _completed(128, ""))

    assert git.run_git("rev-parse", "HEAD", cwd=".") is None


def test_returns_none_when_output_is_blank(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(git.subprocess, "run", lambda *_a, **_k: _completed(0, "\n"))

    assert git.run_git("rev-parse", "--show-toplevel", cwd=".") is None


def test_passes_cwd_and_args_through_to_git(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[list[str]] = []

    def _fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        seen.append(command)
        return _completed(0, "ok")

    monkeypatch.setattr(git.subprocess, "run", _fake_run)

    git.run_git("rev-parse", "HEAD", cwd="/repo")

    assert seen == [["git", "-C", "/repo", "rev-parse", "HEAD"]]
