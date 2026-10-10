from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.checks.python.public_api_test_evidence_check import (
    changed_files,
    changed_public_functions,
    has_nearby_test_change,
)
from tests.scripts.helpers import write_file


def test_changed_public_function_is_detected_from_changed_lines(tmp_path: Path) -> None:
    write_file(
        tmp_path / "scripts/example.py",
        "from __future__ import annotations\n\n\n"
        "def public() -> int:\n"
        "    return 1\n\n\n"
        "def _private() -> int:\n"
        "    return 2\n",
    )

    functions = changed_public_functions(tmp_path, "scripts/example.py", {5})

    assert [(function.path, function.qualname, function.lineno) for function in functions] == [
        ("scripts/example.py", "public", 4)
    ]


def test_changed_public_method_is_detected_from_changed_lines(tmp_path: Path) -> None:
    write_file(
        tmp_path / "scripts/example.py",
        "from __future__ import annotations\n\n\n"
        "class Service:\n"
        "    def run(self) -> int:\n"
        "        return 1\n\n"
        "    def _helper(self) -> int:\n"
        "        return 2\n",
    )

    functions = changed_public_functions(tmp_path, "scripts/example.py", {6})

    assert [(function.path, function.qualname, function.lineno) for function in functions] == [
        ("scripts/example.py", "Service.run", 5)
    ]


def test_nearby_test_change_matches_scripts_mirror() -> None:
    assert has_nearby_test_change("scripts/checks/python/example_check.py", ["tests/scripts/test_example_check.py"])


def test_missing_nearby_test_change_is_false() -> None:
    assert not has_nearby_test_change("scripts/checks/python/example_check.py", ["tests/scripts/test_other.py"])


def test_changed_files_include_untracked_and_non_ascii_names_unquoted(tmp_path: Path) -> None:
    def run(*args: str) -> None:
        subprocess.run(
            ["git", "-c", "user.email=t@example.test", "-c", "user.name=t", *args],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )

    run("init", "-b", "main")
    write_file(tmp_path / "scripts/a.py", "x = 1\n")
    run("add", "-A")
    run("commit", "-m", "base")
    write_file(tmp_path / "scripts/a.py", "x = 2\n")
    write_file(tmp_path / "scripts/módulo.py", "y = 2\n")

    assert changed_files(tmp_path) == ["scripts/a.py", "scripts/módulo.py"]
