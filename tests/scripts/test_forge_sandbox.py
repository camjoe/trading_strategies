import subprocess
from pathlib import Path

import pytest

from scripts.forge.base import ForgeError
from scripts.forge.local import LocalGit
from scripts.forge.sandbox import build_sandbox, sandbox, venv_python


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

        monkeypatch.setattr(sandbox_module.subprocess, "run", slow)

        with pytest.raises(ForgeError, match="timed out"):
            sandbox_module._run(["git", "clone", "x"], tmp_path)


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
