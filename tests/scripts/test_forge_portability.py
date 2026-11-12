"""The review tooling's core modules import only the standard library and each other.

That keeps them usable in another project: only the adapters (github, local, container, sandbox) and the command-line
wiring know about this repository.
"""

import ast
import sys
from pathlib import Path

FORGE = Path(__file__).resolve().parents[2] / "scripts" / "forge"
PORTABLE = ("base", "findings", "readiness", "service", "scorecard", "scorecard_store", "inline")


def _imports(module: str) -> set[str]:
    tree = ast.parse((FORGE / f"{module}.py").read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def test_the_core_modules_depend_only_on_the_standard_library_and_each_other() -> None:
    for module in PORTABLE:
        for name in _imports(module):
            root = name.split(".")[0]
            assert root in sys.stdlib_module_names or name.startswith("scripts.forge."), f"{module} imports {name}"


def test_the_core_modules_do_not_import_an_adapter() -> None:
    adapters = {"scripts.forge.github", "scripts.forge.local", "scripts.forge.container", "scripts.forge.sandbox"}
    for module in PORTABLE:
        assert not (_imports(module) & adapters), module
