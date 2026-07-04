from __future__ import annotations

from pathlib import Path

from scripts.checks.python.python_check import run_python_check


def test_python_check_runs_public_api_test_evidence_step(monkeypatch, tmp_path: Path) -> None:
    calls: list[str] = []

    monkeypatch.setattr(
        "scripts.checks.python.python_check.run_python_conventions_check",
        lambda **_: calls.append("conventions") or 0,
    )
    monkeypatch.setattr(
        "scripts.checks.python.python_check.run_public_api_test_evidence_check",
        lambda **_: calls.append("public-api-test-evidence") or 0,
    )
    monkeypatch.setattr("scripts.checks.python.python_check.run_ruff", lambda **_: calls.append("ruff") or 0)
    monkeypatch.setattr("scripts.checks.python.python_check.run_mypy", lambda **_: calls.append("mypy") or 0)
    monkeypatch.setattr("scripts.checks.python.python_check.run_pytest", lambda **_: calls.append("pytest") or 0)

    exit_code = run_python_check(tmp_path, "python.exe", no_cov=True)

    assert exit_code == 0
    assert calls == ["conventions", "public-api-test-evidence", "ruff", "mypy", "pytest"]
