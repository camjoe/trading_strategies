"""Tests for scripts.checks.python.python_conventions_check."""

from __future__ import annotations

from pathlib import Path

from common.git import get_repo_root
from scripts.checks.python.python_conventions_check import (
    check_file,
    discover_python_files,
    run_python_conventions_check,
)
from tests.scripts.helpers import write_file


def test_valid_module_passes(tmp_path: Path) -> None:
    path = write_file(
        tmp_path / "src/example.py",
        "from __future__ import annotations\n\n\ndef public() -> int:\n    return 1\n",
    )

    assert check_file(path).problems == []


def test_public_function_without_return_annotation_is_reported(tmp_path: Path) -> None:
    path = write_file(
        tmp_path / "src/example.py",
        "from __future__ import annotations\n\n\ndef public():\n    return 1\n",
    )

    assert check_file(path).problems == ["public function `public` missing return annotation at line 4"]


def test_private_function_without_return_annotation_is_allowed(tmp_path: Path) -> None:
    path = write_file(
        tmp_path / "src/example.py",
        "from __future__ import annotations\n\n\ndef _private():\n    return 1\n",
    )

    assert check_file(path).problems == []


def test_discovery_skips_tests_and_init_files(tmp_path: Path) -> None:
    write_file(tmp_path / "src/pkg/__init__.py", "")
    write_file(tmp_path / "tests/test_example.py", "")
    write_file(tmp_path / "src/pkg/module.py", "from __future__ import annotations\n")

    discovered = {path.relative_to(tmp_path).as_posix() for path in discover_python_files(tmp_path)}

    assert discovered == {"src/pkg/module.py"}


def test_real_repo_python_conventions_are_clean() -> None:
    repo_root = get_repo_root(Path(__file__))

    assert run_python_conventions_check(repo_root, enforce=True) == 0
