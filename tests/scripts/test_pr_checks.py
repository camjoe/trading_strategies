from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

import scripts.checks.pr as pr_checks


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@example.test", "-c", "user.name=t", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def _patch_checks(
    monkeypatch, *, diff: list[str], docs_exit: int = 0, quick_exit: int = 0, uncommitted: list[str] | None = None
) -> dict[str, object]:
    calls: dict[str, object] = {"quick": None, "docs": None}

    monkeypatch.setattr(pr_checks, "changed_files", lambda repo_root, base_ref=None: diff)
    monkeypatch.setattr(pr_checks, "uncommitted_files", lambda repo_root: uncommitted or [])
    monkeypatch.setattr(pr_checks, "resolve_ref", lambda repo_root, ref: "abc1234")

    def fake_docs(**kwargs: object) -> int:
        calls["docs"] = kwargs
        return docs_exit

    monkeypatch.setattr(pr_checks, "run_docs_check", fake_docs)

    def fake_quick(**kwargs: object) -> int:
        calls["quick"] = kwargs
        return quick_exit

    monkeypatch.setattr(pr_checks, "run_quick", fake_quick)
    return calls


@pytest.mark.parametrize(
    ("paths", "expected"),
    [
        (["src/trading/services/execution/open_order_reconciliation.py"], False),
        (["apps/paper_trading_web/backend/routes/admin.py"], False),
        (["apps/paper_trading_web/frontend/src/App.tsx"], True),
        ([".github/workflows/ci.yml"], True),
        (["apps\\paper_trading_web\\frontend\\package.json"], True),
        ([], False),
    ],
)
def test_touches_frontend_matches_the_ci_filter(paths: list[str], expected: bool) -> None:
    assert pr_checks.touches_frontend(paths) is expected


def test_run_pr_targets_python_checks_at_the_base_and_skips_the_frontend(monkeypatch, tmp_path: Path) -> None:
    calls = _patch_checks(monkeypatch, diff=["src/trading/domain/broker_connection.py"])

    code = pr_checks.run_pr(tmp_path, "python", base_ref="origin/develop", no_cov=True)

    assert code == 0
    assert calls["quick"] == {
        "repo_root": tmp_path,
        "python_exe": "python",
        "with_frontend": False,
        "suite_base": "origin/develop",
        "no_cov": True,
    }


def test_run_pr_adds_the_frontend_when_the_diff_touches_it(monkeypatch, tmp_path: Path) -> None:
    calls = _patch_checks(monkeypatch, diff=["apps/paper_trading_web/frontend/src/App.tsx"])

    assert pr_checks.run_pr(tmp_path, "python") == 0

    assert calls["quick"]["with_frontend"] is True
    assert calls["quick"]["suite_base"] == pr_checks.DEFAULT_BASE_REF


def test_run_pr_stops_at_a_failing_docs_check(monkeypatch, tmp_path: Path) -> None:
    calls = _patch_checks(monkeypatch, diff=["plan/review-mindsets.md"], docs_exit=1)

    assert pr_checks.run_pr(tmp_path, "python") == 1

    assert calls["quick"] is None


def test_run_pr_returns_the_quick_checks_exit_code(monkeypatch, tmp_path: Path) -> None:
    _patch_checks(monkeypatch, diff=["src/trading/domain/broker_connection.py"], quick_exit=2)

    assert pr_checks.run_pr(tmp_path, "python") == 2


def test_run_pr_reports_a_failing_frontend_step_as_an_exit_code(monkeypatch, tmp_path: Path) -> None:
    _patch_checks(monkeypatch, diff=["apps/paper_trading_web/frontend/src/App.tsx"])

    def failing_quick(**kwargs: object) -> int:
        raise subprocess.CalledProcessError(3, ["npm", "run", "lint"])

    monkeypatch.setattr(pr_checks, "run_quick", failing_quick)

    assert pr_checks.run_pr(tmp_path, "python") == 3


def test_run_pr_fails_without_running_checks_when_the_base_ref_is_unknown(monkeypatch, tmp_path: Path) -> None:
    def unknown_ref(repo_root: Path, base_ref: str | None = None) -> list[str]:
        raise subprocess.CalledProcessError(128, ["git", "diff", "--name-only", f"{base_ref}...HEAD"])

    monkeypatch.setattr(pr_checks, "changed_files", unknown_ref)
    ran: list[str] = []
    monkeypatch.setattr(pr_checks, "run_docs_check", lambda **kwargs: ran.append("docs") or 0)
    monkeypatch.setattr(pr_checks, "run_quick", lambda **kwargs: ran.append("quick") or 0)

    assert pr_checks.run_pr(tmp_path, "python", base_ref="no-such-ref") == 128

    assert ran == []


def test_run_pr_runs_the_docs_check_enforced(monkeypatch, tmp_path: Path) -> None:
    calls = _patch_checks(monkeypatch, diff=["plan/review-mindsets.md"])

    assert pr_checks.run_pr(tmp_path, "python") == 0

    assert calls["docs"] == {"repo_root": tmp_path, "enforce": True, "quiet": True}


def test_run_pr_warns_about_uncommitted_files_and_still_runs(monkeypatch, tmp_path: Path, capsys) -> None:
    calls = _patch_checks(
        monkeypatch,
        diff=["scripts/checks/pr.py"],
        uncommitted=[f"apps/paper_trading_web/frontend/src/f{i}.tsx" for i in range(7)],
    )

    assert pr_checks.run_pr(tmp_path, "python") == 0

    output = capsys.readouterr().out
    assert "WARNING: 7 uncommitted file(s)" in output
    assert "f4.tsx ..." in output
    assert calls["quick"] is not None


def test_uncommitted_files_lists_modified_and_untracked_files(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-b", "main", str(tmp_path)], check=True, capture_output=True)
    (tmp_path / "tracked.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.email=t@example.test", "-c", "user.name=t", "commit", "-m", "base"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    assert pr_checks.uncommitted_files(tmp_path) == []

    (tmp_path / "tracked.py").write_text("x = 2\n", encoding="utf-8")
    (tmp_path / "new.py").write_text("y = 1\n", encoding="utf-8")

    assert sorted(pr_checks.uncommitted_files(tmp_path)) == ["new.py", "tracked.py"]


def test_run_pr_prints_the_base_it_resolved(monkeypatch, tmp_path: Path, capsys) -> None:
    _patch_checks(monkeypatch, diff=["scripts/checks/pr.py"])

    assert pr_checks.run_pr(tmp_path, "python", base_ref="develop") == 0

    assert "Targeting develop...HEAD (base abc1234)" in capsys.readouterr().out


def test_uncommitted_files_returns_plain_paths_for_renames_spaces_and_non_ascii_names(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-b", "main", str(tmp_path))
    (tmp_path / "old.py").write_text("x = 1\n" * 40, encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-m", "base")
    _git(tmp_path, "mv", "old.py", "new.py")
    (tmp_path / "has space.py").write_text("z = 3\n", encoding="utf-8")
    (tmp_path / "módulo.py").write_text("y = 2\n", encoding="utf-8")

    assert sorted(pr_checks.uncommitted_files(tmp_path)) == ["has space.py", "módulo.py", "new.py"]


def test_run_pr_reaches_the_branch_targeted_python_checks_and_the_frontend(monkeypatch, tmp_path: Path) -> None:
    import scripts.checks.quick as quick

    monkeypatch.setattr(
        pr_checks, "changed_files", lambda repo_root, base_ref=None: ["apps/paper_trading_web/frontend/a.ts"]
    )
    monkeypatch.setattr(pr_checks, "resolve_ref", lambda repo_root, ref: "abc1234")
    monkeypatch.setattr(pr_checks, "uncommitted_files", lambda repo_root: [])
    monkeypatch.setattr(pr_checks, "run_docs_check", lambda **kwargs: 0)
    seen: dict[str, object] = {}
    monkeypatch.setattr(quick, "run_repo_check", lambda **kwargs: 0)
    monkeypatch.setattr(quick, "run_python_check", lambda **kwargs: seen.update(python=kwargs) or 0)
    monkeypatch.setattr(quick, "_run_frontend_quick", lambda frontend_dir: seen.update(frontend=frontend_dir))

    assert pr_checks.run_pr(tmp_path, "python", base_ref="origin/develop") == 0

    assert seen["python"]["suite_base"] == "origin/develop"
    assert seen["frontend"] == tmp_path / "apps" / "paper_trading_web" / "frontend"


def test_frontend_paths_match_the_ci_frontend_filter() -> None:
    ci_yml = (Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    block = re.search(r"^\s+frontend_related:\s*\n((?:\s+- .*\n)+)", ci_yml, re.MULTILINE)
    assert block is not None, "ci.yml no longer lists a frontend_related filter"
    ci_paths = [line.strip()[2:].removesuffix("**") for line in block.group(1).splitlines()]

    assert sorted(ci_paths) == sorted(pr_checks.FRONTEND_PATHS)
