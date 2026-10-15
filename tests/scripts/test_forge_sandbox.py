import os
import shutil
import stat
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from scripts.forge.base import ForgeError
from scripts.forge.local import LocalGit
from scripts.forge.sandbox import TRUSTED_CONFIG, Sandbox, build_sandbox, harden_clone, sandbox, scrubbed, venv_python


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repository with a remote-tracking branch, like a checkout that has fetched from GitHub."""
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(remote))
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "develop")
    git(root, "config", "user.name", "Owner")
    git(root, "config", "user.email", "owner@example.test")
    (root / "a.txt").write_text("a", encoding="utf-8")
    (root / ".gitignore").write_text(".venv/\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "first")
    git(root, "remote", "add", "origin", str(remote))
    git(root, "push", "-q", "origin", "develop")
    git(root, "fetch", "-q", "origin")
    return root


class TestBuild:
    def test_the_clone_is_at_the_given_commit_with_the_remote_tracking_refs_the_checks_diff_against(
        self, repo: Path, tmp_path: Path
    ) -> None:
        head = git(repo, "rev-parse", "HEAD")
        (tmp_path / "parent").mkdir()

        box = build_sandbox(repo, head, tmp_path / "parent", install=False)

        assert git(box.path, "rev-parse", "HEAD") == head
        assert git(box.path, "rev-parse", "origin/develop") == head

    def test_the_clone_cannot_reach_the_real_repository_or_any_remote(self, repo: Path, tmp_path: Path) -> None:
        (tmp_path / "parent").mkdir()
        box = build_sandbox(repo, git(repo, "rev-parse", "HEAD"), tmp_path / "parent", install=False)
        (box.path / "x.txt").write_text("x", encoding="utf-8")
        git(box.path, "add", "x.txt")
        git(box.path, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "x")

        pushed = subprocess.run(
            ["git", "push", "origin", "HEAD:refs/heads/x"], cwd=box.path, capture_output=True, text=True
        )

        assert pushed.returncode != 0
        assert subprocess.run(["git", "rev-parse", "--verify", "refs/heads/x"], cwd=repo).returncode != 0
        assert str(repo) not in git(box.path, "remote", "get-url", "origin")

    def test_commits_in_the_clone_carry_the_given_identity(self, repo: Path, tmp_path: Path) -> None:
        (tmp_path / "parent").mkdir()
        box = build_sandbox(
            repo, git(repo, "rev-parse", "HEAD"), tmp_path / "parent", ("Dev", "dev@example.test"), False
        )

        assert (
            git(box.path, "config", "user.name") == "Dev"
            and git(box.path, "config", "user.email") == "dev@example.test"
        )

    def test_an_unknown_commit_is_a_forge_error(self, repo: Path, tmp_path: Path) -> None:
        (tmp_path / "parent").mkdir()

        with pytest.raises(ForgeError, match="Sandbox step failed"):
            build_sandbox(repo, "0" * 40, tmp_path / "parent", install=False)

    def test_the_venv_interpreter_path_follows_the_platform(self, tmp_path: Path) -> None:
        assert venv_python(tmp_path).name in ("python.exe", "python")


class TestIsolation:
    def test_a_commit_made_in_the_clone_reaches_the_checkout_only_when_it_is_imported_and_applied(
        self, repo: Path
    ) -> None:
        local = LocalGit(repo)
        start = local.head()
        with sandbox(repo, start, install=False) as box:
            (box.path / "new.txt").write_text("n", encoding="utf-8")
            git(box.path, "add", "new.txt")
            git(box.path, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "change")
            assert not (repo / "new.txt").exists()
            imported = local.import_commits(box.path, start)

        assert not (repo / "new.txt").exists() and local.head() == start
        local.fast_forward(imported)
        assert (repo / "new.txt").exists()

    def test_hooks_config_and_planted_files_in_the_clone_never_reach_the_checkout(self, repo: Path) -> None:
        local = LocalGit(repo)
        start = local.head()
        config_before = (repo / ".git" / "config").read_text(encoding="utf-8")
        with sandbox(repo, start, install=False) as box:
            hooks = box.path / ".git" / "hooks"
            hooks.mkdir(exist_ok=True)
            (hooks / "pre-push").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            with (box.path / ".git" / "config").open("a", encoding="utf-8") as config:
                config.write("[core]\n\thooksPath = /tmp/evil\n\tfsmonitor = /tmp/evil\n")
            (box.path / ".venv").mkdir()
            (box.path / ".venv" / "sitecustomize.py").write_text("raise SystemExit", encoding="utf-8")
            (box.path / "tracked-change.txt").write_text("c", encoding="utf-8")
            git(box.path, "add", "tracked-change.txt")
            git(box.path, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "c")
            imported = local.import_commits(box.path, start)
        local.fast_forward(imported)

        assert not (repo / ".git" / "hooks" / "pre-push").exists()
        assert (repo / ".git" / "config").read_text(encoding="utf-8") == config_before
        assert not (repo / ".venv").exists()
        assert local.changed_paths(start, local.head()) == ["tracked-change.txt"]

    def test_commits_that_rewrite_history_are_refused_at_import(self, repo: Path) -> None:
        local = LocalGit(repo)
        (repo / "b.txt").write_text("b", encoding="utf-8")
        git(repo, "add", "b.txt")
        git(repo, "commit", "-q", "-m", "second")
        start = local.head()
        with sandbox(repo, start, install=False) as box:
            git(box.path, "reset", "-q", "--hard", "HEAD~1")
            (box.path / "other.txt").write_text("o", encoding="utf-8")
            git(box.path, "add", "other.txt")
            git(box.path, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "rewrite")

            with pytest.raises(ForgeError, match="do not descend"):
                local.import_commits(box.path, start)

    def test_uncommitted_files_are_listed_and_ignored_ones_are_not(self, repo: Path) -> None:
        with sandbox(repo, git(repo, "rev-parse", "HEAD"), install=False) as box:
            (box.path / "a.txt").write_text("changed", encoding="utf-8")
            (box.path / "new.txt").write_text("n", encoding="utf-8")
            (box.path / ".venv").mkdir()
            (box.path / ".venv" / "x.py").write_text("x", encoding="utf-8")

            listed = box.uncommitted()

        assert sorted(line[3:] for line in listed) == ["a.txt", "new.txt"]


class TestCleanup:
    def test_the_sandbox_is_deleted_when_the_block_ends_including_read_only_git_files(self, repo: Path) -> None:
        with sandbox(repo, git(repo, "rev-parse", "HEAD"), install=False) as box:
            parent = box.path.parent
            assert parent.exists()

        assert not parent.exists()

    def test_the_sandbox_is_deleted_when_the_block_raises(self, repo: Path) -> None:
        seen: list[Path] = []

        with pytest.raises(RuntimeError):
            with sandbox(repo, git(repo, "rev-parse", "HEAD"), install=False) as box:
                seen.append(box.path.parent)
                raise RuntimeError("agent failed")

        assert not seen[0].exists()


class TestInstallAndTimeouts:
    def test_the_install_path_creates_a_venv_and_installs_the_dev_requirements_inside_it(
        self, repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from scripts.forge import sandbox as sandbox_module

        commands: list[list[str]] = []
        real_run = sandbox_module._run

        def record(args: list[str], cwd: Path) -> None:
            commands.append(args)
            if args[:3] == [sandbox_module.sys.executable, "-m", "venv"] or "pip" in args:
                return
            real_run(args, cwd)

        monkeypatch.setattr(sandbox_module, "_run", record)
        (tmp_path / "parent").mkdir()

        box = build_sandbox(repo, git(repo, "rev-parse", "HEAD"), tmp_path / "parent")

        venv = [command for command in commands if command[1:3] == ["-m", "venv"]]
        pip = [command for command in commands if "pip" in command]
        assert venv and venv[0][-1] == str(box.path / ".venv")
        assert pip and pip[0][0] == str(venv_python(box.path / ".venv")) and "requirements-dev.txt" in pip[0]

    def test_a_step_that_never_finishes_is_a_forge_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from scripts.forge import sandbox as sandbox_module

        def slow(*_a: object, **_k: object) -> None:
            raise subprocess.TimeoutExpired("git", 1)

        monkeypatch.setattr(sandbox_module, "run_bounded", slow)

        with pytest.raises(ForgeError, match="timed out"):
            sandbox_module._run(["git", "clone", "x"], tmp_path)

    def test_a_timeout_kills_a_grandchild_that_holds_the_output_pipes(self, tmp_path: Path) -> None:
        import sys
        import time

        from scripts.forge.sandbox import run_bounded

        code = (
            "import subprocess, sys, time\n"
            "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
            "time.sleep(60)\n"
        )
        started = time.monotonic()

        with pytest.raises(subprocess.TimeoutExpired):
            run_bounded([sys.executable, "-c", code], tmp_path, timeout=2)

        assert time.monotonic() - started < 30

    def test_run_bounded_feeds_the_input_text_to_stdin(self, tmp_path: Path) -> None:
        import sys

        from scripts.forge.sandbox import run_bounded

        code = "import sys; sys.stdin.reconfigure(encoding='utf-8'); sys.stdout.reconfigure(encoding='utf-8'); print(sys.stdin.read().upper())"

        completed = run_bounded([sys.executable, "-c", code], tmp_path, input_text="héllo\nworld")

        assert completed.stdout.strip().splitlines() == ["HÉLLO", "WORLD"]

    def test_uncommitted_fails_outside_a_repository(self, tmp_path: Path) -> None:
        from scripts.forge.sandbox import Sandbox

        (tmp_path / ".git").mkdir()

        with pytest.raises(ForgeError, match="git status"):
            Sandbox(tmp_path).uncommitted()


def test_the_cli_factory_cuts_sandboxes_from_this_repository_with_the_owners_identity(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.forge import cli

    monkeypatch.setattr(cli, "get_repo_root", lambda: repo)
    git(repo, "config", "user.name", "Owner")
    git(repo, "config", "user.email", "owner@example.test")
    factory = cli._sandbox_factory(LocalGit(repo))

    with factory(git(repo, "rev-parse", "HEAD"), install=False) as box:
        assert git(box.path, "config", "user.name") == "Owner"
        assert git(box.path, "rev-parse", "HEAD") == git(repo, "rev-parse", "HEAD")


class TestImportAncestry:
    def test_a_git_error_is_reported_as_one_not_as_a_history_rewrite(self, repo: Path, tmp_path: Path) -> None:
        local = LocalGit(repo)
        (tmp_path / "parent").mkdir()
        box = build_sandbox(repo, git(repo, "rev-parse", "HEAD"), tmp_path / "parent", install=False)

        with pytest.raises(ForgeError, match="merge-base failed"):
            local.import_commits(box.path, "not-a-commit")


def test_a_directory_that_cannot_be_deleted_is_reported_and_does_not_replace_the_result(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from scripts.forge import sandbox as sandbox_module

    real_rmtree = sandbox_module.shutil.rmtree

    def fail(path: object, *args: object, **kwargs: object) -> None:
        if kwargs.get("ignore_errors"):
            return real_rmtree(path, *args, **kwargs)  # type: ignore[arg-type]
        raise PermissionError("locked")

    monkeypatch.setattr(sandbox_module.shutil, "rmtree", fail)

    with sandbox_module.sandbox(repo, git(repo, "rev-parse", "HEAD"), install=False) as box:
        parent = box.path.parent

    assert "remove it by hand" in capsys.readouterr().err
    monkeypatch.undo()
    sandbox_module.shutil.rmtree(parent, onexc=sandbox_module._make_writable)


class TestProcessGroupPerPlatform:
    def _popen_kwargs(self, monkeypatch: pytest.MonkeyPatch, platform: str, tmp_path: Path) -> dict[str, object]:
        from scripts.forge import sandbox as sandbox_module

        seen: dict[str, object] = {}

        class FakeProcess:
            pid = 1
            returncode = 0

            def __init__(self, *_args: object, **kwargs: object) -> None:
                seen.update(kwargs)

            def __enter__(self) -> "FakeProcess":
                return self

            def __exit__(self, *_exc: object) -> None:
                return None

            def communicate(self, input: str | None = None, timeout: float | None = None) -> tuple[str, str]:
                return "", ""

        monkeypatch.setattr(sandbox_module.sys, "platform", platform)
        monkeypatch.setattr(sandbox_module.subprocess, "Popen", FakeProcess)
        sandbox_module.run_bounded(["x"], tmp_path)
        return seen

    def test_windows_starts_a_new_process_group(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        seen = self._popen_kwargs(monkeypatch, "win32", tmp_path)

        assert "creationflags" in seen and "start_new_session" not in seen

    def test_other_platforms_start_a_new_session(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        seen = self._popen_kwargs(monkeypatch, "linux", tmp_path)

        assert seen.get("start_new_session") is True and "creationflags" not in seen


def test_the_clone_carries_no_trace_of_the_owners_repository_path(repo: Path, tmp_path: Path) -> None:
    (tmp_path / "parent").mkdir()
    box = build_sandbox(repo, git(repo, "rev-parse", "HEAD"), tmp_path / "parent", install=False)

    assert not (box.path / ".git" / "FETCH_HEAD").exists() and not (box.path / ".git" / "logs").exists()
    found = [
        path
        for path in (box.path / ".git").rglob("*")
        if path.is_file() and str(repo).encode() in path.read_bytes() and path.name != "index"
    ]
    assert found == []


def test_a_status_read_that_never_finishes_is_a_forge_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.forge import sandbox as sandbox_module
    from scripts.forge.sandbox import Sandbox

    def slow(*_a: object, **_k: object) -> None:
        raise subprocess.TimeoutExpired("git", 1)

    monkeypatch.setattr(sandbox_module, "run_bounded", slow)
    (tmp_path / ".git").mkdir()

    with pytest.raises(ForgeError, match="timed out"):
        Sandbox(tmp_path).uncommitted()


class TestReadAgentText:
    def test_a_missing_file_is_empty_and_a_plain_file_is_read(self, tmp_path: Path) -> None:
        from scripts.forge.sandbox import read_agent_text

        (tmp_path / "a.md").write_text("hello", encoding="utf-8")

        assert read_agent_text(tmp_path / "missing.md") == ""
        assert read_agent_text(tmp_path / "a.md") == "hello"

    def test_a_directory_is_refused(self, tmp_path: Path) -> None:
        from scripts.forge.sandbox import read_agent_text

        (tmp_path / "d.md").mkdir()

        with pytest.raises(ForgeError, match="not a plain file"):
            read_agent_text(tmp_path / "d.md")

    def test_a_symbolic_link_is_refused_and_its_target_is_not_read(self, tmp_path: Path) -> None:
        from scripts.forge.sandbox import read_agent_text

        target = tmp_path / "private.txt"
        target.write_text("host secret", encoding="utf-8")
        try:
            (tmp_path / "q.md").symlink_to(target)
        except OSError, NotImplementedError:
            pytest.skip("symbolic links cannot be created here")

        with pytest.raises(ForgeError, match="not a plain file"):
            read_agent_text(tmp_path / "q.md")

    def test_a_windows_reparse_point_is_refused(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import types

        from scripts.forge.sandbox import read_agent_text

        (tmp_path / "q.md").write_text("x", encoding="utf-8")
        link = types.SimpleNamespace(
            st_mode=stat.S_IFREG | 0o644, st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT
        )
        monkeypatch.setattr(Path, "lstat", lambda self: link)

        with pytest.raises(ForgeError, match="not a plain file"):
            read_agent_text(tmp_path / "q.md")

    def test_a_file_that_cannot_be_inspected_is_refused(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from scripts.forge.sandbox import read_agent_text

        def unreadable(self: Path) -> None:
            raise PermissionError("denied")

        monkeypatch.setattr(Path, "lstat", unreadable)

        with pytest.raises(ForgeError, match="could not be inspected"):
            read_agent_text(tmp_path / "q.md")


class TestScrubbed:
    ENVIRONMENT = {
        "PATH": "p",
        "GITHUB_TOKEN": "t",
        "CLAUDE_CODE_OAUTH_TOKEN": "c",
        "ANTHROPIC_API_KEY": "a",
        "MY_SECRET": "s",
    }

    def test_secret_looking_names_are_dropped(self) -> None:
        assert scrubbed(self.ENVIRONMENT) == {"PATH": "p"}

    def test_names_with_a_kept_prefix_survive_and_other_secret_names_are_still_dropped(self) -> None:
        kept = scrubbed(self.ENVIRONMENT, ("CLAUDE", "ANTHROPIC"))

        assert kept == {"PATH": "p", "CLAUDE_CODE_OAUTH_TOKEN": "c", "ANTHROPIC_API_KEY": "a"}


class TestHardening:
    def _box(self, repo: Path, tmp_path: Path) -> Sandbox:
        parent = tmp_path / "parent"
        parent.mkdir()
        return build_sandbox(repo, git(repo, "rev-parse", "HEAD"), parent, install=False)

    def _plant_fsmonitor(self, box: Sandbox, marker: Path) -> None:
        with (box.path / ".git" / "config").open("a", encoding="utf-8") as config:
            config.write(f"[core]{chr(10)}{chr(9)}fsmonitor = echo hit > {marker.as_posix()}{chr(10)}")

    def _control(self, box: Sandbox, marker: Path) -> None:
        subprocess.run(["git", "status"], cwd=box.path, capture_output=True, check=False)
        if not marker.exists():
            pytest.skip("this git does not run a configured fsmonitor command, so the plant proves nothing")
        marker.unlink()

    def test_a_command_planted_in_the_clones_config_does_not_run_when_the_controller_checks_it(
        self, repo: Path, tmp_path: Path
    ) -> None:
        box = self._box(repo, tmp_path)
        marker = tmp_path / "marker"
        self._plant_fsmonitor(box, marker)
        self._control(box, marker)

        assert box.uncommitted() == []

        assert not marker.exists()
        assert "fsmonitor" not in (box.path / ".git" / "config").read_text(encoding="utf-8")

    def test_a_command_planted_in_the_clones_config_does_not_run_when_its_commits_are_imported(
        self, repo: Path, tmp_path: Path
    ) -> None:
        box = self._box(repo, tmp_path)
        marker = tmp_path / "marker"
        self._plant_fsmonitor(box, marker)
        self._control(box, marker)

        imported = LocalGit(repo).import_commits(box.path, git(repo, "rev-parse", "HEAD"))

        assert imported == git(repo, "rev-parse", "HEAD")
        assert not marker.exists()
        assert "fsmonitor" not in (box.path / ".git" / "config").read_text(encoding="utf-8")

    def test_the_trusted_config_is_restored_and_hooks_and_alternates_are_removed(
        self, repo: Path, tmp_path: Path
    ) -> None:
        box = self._box(repo, tmp_path)
        trusted = (box.path.parent / TRUSTED_CONFIG).read_text(encoding="utf-8")
        git_dir = box.path / ".git"
        (git_dir / "config").write_text("[alias]" + chr(10) + chr(9) + "x = !echo" + chr(10), encoding="utf-8")
        (git_dir / "hooks").mkdir(exist_ok=True)
        (git_dir / "hooks" / "pre-commit").write_text("exit 0", encoding="utf-8")
        (git_dir / "objects" / "info").mkdir(parents=True, exist_ok=True)
        (git_dir / "objects" / "info" / "alternates").write_text("/elsewhere", encoding="utf-8")
        (git_dir / "info").mkdir(exist_ok=True)
        (git_dir / "info" / "attributes").write_text("* filter=x", encoding="utf-8")

        harden_clone(box.path)

        assert (git_dir / "config").read_text(encoding="utf-8") == trusted
        assert not (git_dir / "hooks").exists()
        assert not (git_dir / "objects" / "info" / "alternates").exists()
        assert not (git_dir / "info" / "attributes").exists()

    def test_a_symlinked_config_is_replaced_and_its_target_is_left_alone(self, repo: Path, tmp_path: Path) -> None:
        box = self._box(repo, tmp_path)
        outside = tmp_path / "outside.txt"
        outside.write_text("keep me", encoding="utf-8")
        config = box.path / ".git" / "config"
        config.unlink()
        try:
            config.symlink_to(outside)
        except OSError, NotImplementedError:
            pytest.skip("symbolic links cannot be created here")

        harden_clone(box.path)

        assert not config.is_symlink() and outside.read_text(encoding="utf-8") == "keep me"
        assert config.read_text(encoding="utf-8") == (box.path.parent / TRUSTED_CONFIG).read_text(encoding="utf-8")

    def test_a_git_directory_that_is_not_a_plain_directory_is_refused(self, repo: Path, tmp_path: Path) -> None:
        box = self._box(repo, tmp_path)

        def make_writable_then_retry(function: Callable[[str], object], path: str, _exc: object) -> None:
            os.chmod(path, stat.S_IWRITE)
            function(path)

        shutil.rmtree(box.path / ".git", onexc=make_writable_then_retry)
        (box.path / ".git").write_text("gitdir: /elsewhere", encoding="utf-8")

        with pytest.raises(ForgeError, match="not a plain directory"):
            box.uncommitted()

    def test_worktree_redirection_files_are_removed(self, repo: Path, tmp_path: Path) -> None:
        box = self._box(repo, tmp_path)
        git_dir = box.path / ".git"
        (git_dir / "commondir").write_text("/elsewhere/.git", encoding="utf-8")
        (git_dir / "config.worktree").write_text("[core]", encoding="utf-8")

        harden_clone(box.path)

        assert not (git_dir / "commondir").exists() and not (git_dir / "config.worktree").exists()

    def test_a_clone_that_cannot_be_cleaned_is_refused_not_used(
        self, repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from scripts.forge import sandbox as sandbox_module

        box = self._box(repo, tmp_path)

        def denied(path: Path) -> None:
            raise PermissionError("denied")

        monkeypatch.setattr(sandbox_module, "_remove", denied)

        with pytest.raises(ForgeError, match="could not be cleaned"):
            harden_clone(box.path)

    def test_a_sandbox_without_a_saved_config_is_still_cleaned_of_hooks(self, tmp_path: Path) -> None:
        (tmp_path / ".git" / "hooks").mkdir(parents=True)
        (tmp_path / ".git" / "hooks" / "post-checkout").write_text("exit 0", encoding="utf-8")
        (tmp_path / ".git" / "config").write_text("[core]", encoding="utf-8")

        harden_clone(tmp_path)

        assert not (tmp_path / ".git" / "hooks").exists()
        assert (tmp_path / ".git" / "config").read_text(encoding="utf-8") == "[core]"

    def test_git_status_runs_without_hooks_or_fsmonitor_and_without_the_owners_secrets(
        self, repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from scripts.forge import sandbox as sandbox_module

        box = self._box(repo, tmp_path)
        seen: dict[str, Any] = {}

        def fake(
            args: list[str], cwd: Path, timeout: float = 0, env: dict[str, str] | None = None, **_k: object
        ) -> "subprocess.CompletedProcess[str]":
            seen.update(args=args, env=env)
            return subprocess.CompletedProcess(args, 0, "", "")

        monkeypatch.setattr(sandbox_module, "run_bounded", fake)
        monkeypatch.setenv("GH_TOKEN", "owner-secret")
        monkeypatch.setenv("TRADING_RUNTIME_ALERT_SMTP_PASSWORD", "owner-secret")

        box.uncommitted()

        assert "core.fsmonitor=false" in seen["args"] and any("core.hooksPath" in a for a in seen["args"])
        env = seen["env"]
        assert isinstance(env, dict) and "GH_TOKEN" not in env and "TRADING_RUNTIME_ALERT_SMTP_PASSWORD" not in env
        assert "PATH" in env or "Path" in env
