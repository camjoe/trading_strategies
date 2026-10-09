from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import scripts.checks.pr as pr_checks


def _patch_checks(monkeypatch, *, diff: list[str], docs_exit: int = 0, quick_exit: int = 0) -> dict[str, object]:
    calls: dict[str, object] = {"quick": None}

    monkeypatch.setattr(pr_checks, "changed_files", lambda repo_root, base_ref=None: diff)
    monkeypatch.setattr(pr_checks, "run_docs_check", lambda **kwargs: docs_exit)

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
