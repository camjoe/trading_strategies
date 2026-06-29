from __future__ import annotations

import sys

from common.paths.executables import resolve_repo_python_exe
from common.paths.formatting import relative_posix


def test_relative_posix_uses_forward_slashes(tmp_path) -> None:
    path = tmp_path / "a" / "b" / "file.txt"
    path.parent.mkdir(parents=True)
    path.write_text("x", encoding="utf-8")

    assert relative_posix(path, tmp_path) == "a/b/file.txt"


def test_resolve_repo_python_exe_prefers_windows_venv_layout(tmp_path) -> None:
    python_exe = tmp_path / ".venv" / "Scripts" / "python.exe"
    python_exe.parent.mkdir(parents=True)
    python_exe.write_text("", encoding="utf-8")

    assert resolve_repo_python_exe(tmp_path) == str(python_exe)


def test_resolve_repo_python_exe_prefers_posix_venv_layout_when_windows_missing(tmp_path) -> None:
    python_exe = tmp_path / ".venv" / "bin" / "python"
    python_exe.parent.mkdir(parents=True)
    python_exe.write_text("", encoding="utf-8")

    assert resolve_repo_python_exe(tmp_path) == str(python_exe)


def test_resolve_repo_python_exe_falls_back_to_current_interpreter(tmp_path) -> None:
    assert resolve_repo_python_exe(tmp_path) == sys.executable
