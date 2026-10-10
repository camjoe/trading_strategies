from __future__ import annotations

import sys

from scripts.checks._runner import CheckStep, resolve_python_exe, run_check_steps


def test_run_check_steps_stops_on_first_failure() -> None:
    calls: list[str] = []

    result = run_check_steps(
        [
            CheckStep("first", lambda: calls.append("first") or 0),
            CheckStep("second", lambda: calls.append("second") or 3),
            CheckStep("third", lambda: calls.append("third") or 0),
        ]
    )

    assert result == 3
    assert calls == ["first", "second"]


def test_run_check_steps_skips_marked_steps() -> None:
    calls: list[str] = []

    result = run_check_steps(
        [
            CheckStep("skip me", lambda: calls.append("skip me") or 1, skip=True),
            CheckStep("run me", lambda: calls.append("run me") or None),
        ]
    )

    assert result == 0
    assert calls == ["run me"]


def test_resolve_python_exe_prefers_windows_venv_layout(tmp_path) -> None:
    python_exe = tmp_path / ".venv" / "Scripts" / "python.exe"
    python_exe.parent.mkdir(parents=True)
    python_exe.write_text("", encoding="utf-8")

    assert resolve_python_exe(tmp_path) == str(python_exe)


def test_resolve_python_exe_prefers_posix_venv_layout_when_windows_missing(tmp_path) -> None:
    python_exe = tmp_path / ".venv" / "bin" / "python"
    python_exe.parent.mkdir(parents=True)
    python_exe.write_text("", encoding="utf-8")

    assert resolve_python_exe(tmp_path) == str(python_exe)


def test_resolve_python_exe_falls_back_to_current_interpreter(tmp_path) -> None:
    assert resolve_python_exe(tmp_path) == sys.executable
