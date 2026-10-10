from __future__ import annotations

import ast
from pathlib import Path

from scripts.checks.python.function_complexity_check import analyze_function, check_file
from tests.scripts.helpers import write_file


def _first_function(source: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    tree = ast.parse(source)
    node = tree.body[0]
    assert isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    return node


def test_small_function_has_no_finding() -> None:
    source = "def simple(value: int) -> int:\n    return value + 1\n"

    assert analyze_function("simple", _first_function(source), "scripts/example.py") is None


def test_many_branches_are_reported() -> None:
    source = "def branchy(value: int) -> int:\n"
    for index in range(13):
        source += f"    if value == {index}:\n        return {index}\n"
    source += "    return value\n"

    finding = analyze_function("branchy", _first_function(source), "scripts/example.py")

    assert finding is not None
    assert "13 branches" in finding.reasons


def test_changed_function_complexity_is_reported_for_changed_lines(tmp_path: Path) -> None:
    source = "def branchy(value: int) -> int:\n"
    for index in range(13):
        source += f"    if value == {index}:\n        return {index}\n"
    source += "    return value\n"
    write_file(tmp_path / "scripts/example.py", source)

    report = check_file(tmp_path, "scripts/example.py", {5})

    assert report.changed_functions == 1
    assert [(finding.path, finding.qualname, finding.lineno) for finding in report.findings] == [
        ("scripts/example.py", "branchy", 1)
    ]
