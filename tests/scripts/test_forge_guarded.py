import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.forge.guarded_paths import guarded_paths_touched

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "path",
    [
        "scripts/checks/repo/review_scope_check.py",
        "scripts/run_checks.py",
        "src/common/git.py",
        ".github/CODEOWNERS",
        ".claude/settings.json",
        "pyproject.toml",
        "pytest.ini",
        "ruff.toml",
        "requirements-dev.txt",
        "tests/scripts/conftest.py",
        "apps/web/.env",
        "apps/web/.env.local",
        ".envrc",
        ".gitattributes",
        "docs/architecture/architecture-conventions.md",
        "src/trading/domain/accounting/ledger.py",
    ],
)
def test_pipeline_gate_and_configuration_paths_are_guarded(path: str) -> None:
    assert [entry.split(":")[0] for entry in guarded_paths_touched([path])] == [path]


@pytest.mark.parametrize(
    "path",
    [
        "src/common/tickers.py",
        "src/common/time.py",
        "tests/scripts/test_forge.py",
        "docs/maps/scripts-map.md",
        "plan/x.md",
    ],
)
def test_ordinary_source_tests_and_docs_are_not_guarded(path: str) -> None:
    assert guarded_paths_touched([path]) == []


@pytest.mark.parametrize("path", ["docker/gate/Dockerfile", "docker/README.md", "Docker/Gate/Dockerfile"])
def test_the_container_directory_is_guarded_whatever_its_case(path: str) -> None:
    assert [entry.split(":")[0] for entry in guarded_paths_touched([path])] == [path]


@pytest.mark.parametrize("path", ["docs/docker-notes.md", "dockerish/x.py", "src/docker/x.py"])
def test_paths_that_only_resemble_the_container_directory_are_not_guarded(path: str) -> None:
    assert guarded_paths_touched([path]) == []


def test_tool_configuration_the_checks_execute_is_guarded() -> None:
    touched = guarded_paths_touched(
        ["mypy.ini", ".flake8", "apps/x/frontend/vite.config.ts", "apps/x/frontend/eslint.config.js"]
    )

    assert len(touched) == 4


@pytest.mark.parametrize(
    "path",
    [
        ".githooks/pre-push",
        ".husky/pre-commit",
        "package.json",
        "package-lock.json",
        "Makefile",
        "tox.ini",
        "setup.cfg",
        "setup.py",
        "noxfile.py",
        ".coveragerc",
        "apps/web/package.json",
        ".env.local",
    ],
)
def test_executed_files_and_hook_directories_are_guarded(path: str) -> None:
    assert len(guarded_paths_touched([path])) == 1


@pytest.mark.parametrize("path", ["src/common/thing.py", "docs/notes.md", "tests/scripts/test_x.py", "README.md"])
def test_ordinary_files_are_not_guarded(path: str) -> None:
    assert guarded_paths_touched([path]) == []


@pytest.mark.parametrize(
    "path", ["Scripts/Forge/guarded_paths.py", ".GitHub/workflows/x.yml", "AGENTS.MD", "Conftest.py", "PYTEST.INI"]
)
def test_the_guard_ignores_case_so_a_case_insensitive_checkout_cannot_dodge_it(path: str) -> None:
    assert len(guarded_paths_touched([path])) == 1


@pytest.mark.parametrize("path", ["apps/web/.githooks/pre-push", "tools/.husky/pre-commit"])
def test_hook_directories_are_guarded_at_any_depth(path: str) -> None:
    assert len(guarded_paths_touched([path])) == 1


@pytest.mark.parametrize("path", ["Apps/.GitHooks/pre-push", "x/.HUSKY/pre-commit", ".ENV.production", "NOXFILE.PY"])
def test_mixed_case_hook_directories_and_executed_names_are_guarded(path: str) -> None:
    assert len(guarded_paths_touched([path])) == 1


@pytest.mark.parametrize(
    "path",
    [
        "scripts/__init__.py",
        "scripts/data_ops/anything.py",
        "src/common/__init__.py",
        "src/__init__.py",
        "tests/sitecustomize.py",
        "venvs/site/extra.pth",
        "USERCUSTOMIZE.PY",
    ],
)
def test_everything_the_workflows_import_and_every_run_on_start_file_is_guarded(path: str) -> None:
    assert len(guarded_paths_touched([path])) == 1


@pytest.mark.parametrize(
    "path, reason",
    [
        ("tests/sitecustomize.py", "code Python runs when it starts"),
        ("venvs/site/extra.pth", "code Python runs when it starts"),
        ("USERCUSTOMIZE.PY", "code Python runs when it starts"),
    ],
)
def test_run_on_start_files_are_guarded_for_that_reason(path: str, reason: str) -> None:
    assert guarded_paths_touched([path]) == [f"{path}: {reason}"]


def _common_modules_imported_by(source: str) -> set[str]:
    import ast

    modules: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            parts = node.module.split(".")
            if parts[0] == "common":
                modules |= {parts[1]} if len(parts) > 1 else {alias.name for alias in node.names} | {"__init__"}
        elif isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split(".")
                if parts[0] == "common":
                    modules.add(parts[1] if len(parts) > 1 else "__init__")
    return modules


def test_the_import_walk_sees_every_way_of_importing_a_common_module() -> None:
    source = "import common\nimport common.git\nfrom common import time\nfrom common.fs import x\nfrom . import y\n"

    assert _common_modules_imported_by(source) == {"__init__", "git", "time", "fs"}


def test_every_common_module_the_forge_tool_imports_is_a_guarded_path() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    modules: set[str] = set()
    for source in (root / "scripts" / "forge").rglob("*.py"):
        modules |= _common_modules_imported_by(source.read_text(encoding="utf-8"))

    assert "git" in modules
    for module in modules:
        assert guarded_paths_touched([f"src/common/{module}.py"]), module


@pytest.mark.parametrize(
    "name", ["vite.config.ts", "eslint.config.mjs", "jest.config.js", ".eslintrc", ".eslintrc.json"]
)
def test_tool_configuration_files_are_guarded_by_exact_name(name: str) -> None:
    assert len(guarded_paths_touched([f"apps/web/{name}"])) == 1


@pytest.mark.parametrize(
    "name", [".eslintrc-notes.md", "vite.config.notes.md", "eslint.config", "my.eslint.config.ts"]
)
def test_lookalike_names_are_not_guarded(name: str) -> None:
    assert guarded_paths_touched([f"docs/{name}"]) == []


@pytest.mark.parametrize(
    "name",
    [
        "vite.config.base.ts",
        "vitest.config.shared.mts",
        "eslint.config.local.js",
        "jest.config.d.ts",
        "vite.config.ts",
    ],
)
def test_config_helper_files_the_gate_can_execute_stay_guarded(name: str) -> None:
    assert len(guarded_paths_touched([f"apps/web/{name}"])) == 1


def test_the_common_package_init_is_guarded_directly() -> None:
    assert guarded_paths_touched(["src/common/__init__.py"]) != []


@pytest.mark.parametrize(
    "name",
    [".eslintrc.base.json", ".eslintrc.local.cjs", "eslint.config.my-local.js", "vite.config.shared.cts", ".eslintrc"],
)
def test_helper_files_with_dotted_or_hyphenated_infixes_are_guarded(name: str) -> None:
    assert len(guarded_paths_touched([f"apps/web/{name}"])) == 1


@pytest.mark.parametrize(
    "name", ["vite.config.ts.bak", "vite.config.md", "vite.config.", "xvite.config.ts", "eslint.config.ts\n"]
)
def test_backup_and_prose_lookalikes_are_not_guarded(name: str) -> None:
    assert guarded_paths_touched([f"docs/{name}"]) == []


@pytest.mark.parametrize(
    "path",
    [
        "apps/web/vite.config.ts.",
        "apps/web/jest.config.js ",
        "apps/web/.eslintrc.",
        "tests/conftest.py.",
        "tools/setup.py ..",
        "x/extra.pth.",
        "apps/.env.",
        "Scripts./forge/guarded_paths.py",
        "scripts/forge./cli.py",
        ".github./workflows/x.yml",
        "apps/web/vite.config.ts::$DATA",
        "apps/web/vite.config.ts:stream",
        "AGENTS.md:Zone.Identifier",
        "apps/web/VITE~1.TS",
        "SCRIPT~1/anything.py",
    ],
)
def test_names_that_windows_resolves_to_a_guarded_file_are_guarded(path: str) -> None:
    assert len(guarded_paths_touched([path])) == 1


@pytest.mark.parametrize("path", ["docs/notes.md.", "src/common/thing.py ", "docs/a:b.md", "tests/scripts/test_x.py"])
def test_the_normalization_does_not_guard_ordinary_files(path: str) -> None:
    assert guarded_paths_touched([path]) == []


@pytest.mark.parametrize(
    "path",
    [
        "./scripts/x.py",
        "docs/../scripts/forge/cli.py",
        "docs/./../AGENTS.md",
        "/scripts/x.py",
        "C:/repo/scripts/x.py",
        "../outside.txt",
    ],
)
def test_dot_segments_are_resolved_and_paths_outside_the_repository_are_guarded(path: str) -> None:
    result = guarded_paths_touched([path])

    assert len(result) == 1 and result[0].startswith(f"{path}: ")


@pytest.mark.parametrize("path", ["docs/./notes.md", "docs/a/../notes.md", "./docs/notes.md"])
def test_resolving_dot_segments_does_not_guard_ordinary_files(path: str) -> None:
    assert guarded_paths_touched([path]) == []


@pytest.mark.parametrize("path", ["apps/web/VITE~1.TS", "src/foo~3/bar.py", "docs/notes~1.md"])
def test_components_shaped_like_short_names_are_guarded(path: str) -> None:
    assert len(guarded_paths_touched([path])) == 1


@pytest.mark.parametrize("path", ["docs/longername~1/x.md", "docs/a~b.txt", "docs/x~.md", "docs/readme~backup"])
def test_tildes_that_are_not_short_name_shaped_are_not_guarded(path: str) -> None:
    assert guarded_paths_touched([path]) == []


OUTSIDE = "a path outside the repository, or not relative to it"
SHORT = "a name that may be a Windows short name for a guarded file"


@pytest.mark.parametrize("path", ["/abs/x.py", "C:x", "C:/repo/x", "//host/share/x", "docs/../../x", "../x"])
def test_paths_outside_the_repository_are_reported_with_that_reason(path: str) -> None:
    assert guarded_paths_touched([path]) == [f"{path}: {OUTSIDE}"]


@pytest.mark.parametrize(
    "path, guarded",
    [
        ("docs/abcdef~1", True),
        ("docs/abcdefg~1", False),
        ("docs/a~1234567", True),
        ("docs/a~12345678", False),
        ("docs/a~1.abc", True),
        ("docs/a~1.abcd", False),
        ("docs/ab~1.", True),
    ],
)
def test_the_short_name_shape_has_exact_limits(path: str, guarded: bool) -> None:
    assert (guarded_paths_touched([path]) == [f"{path}: {SHORT}"]) is guarded


def test_backslash_traversal_is_resolved_before_matching() -> None:
    path = "docs" + chr(92) + ".." + chr(92) + "scripts" + chr(92) + "forge" + chr(92) + "x.py"

    assert len(guarded_paths_touched([path])) == 1 and OUTSIDE not in guarded_paths_touched([path])[0]


@pytest.mark.parametrize("path", ["", ".", "a/.../b", "docs/./"])
def test_empty_and_dot_only_paths_are_not_guarded(path: str) -> None:
    assert guarded_paths_touched([path]) == []


PROBE = chr(10).join(
    [
        "import json, sys",
        "from pathlib import Path",
        "import scripts.checks.repo.review_scope_check",
        "root = Path.cwd().resolve()",
        "found = set()",
        "for module in list(sys.modules.values()):",
        "    file = getattr(module, '__file__', None)",
        "    resolved = Path(file).resolve() if file else None",
        "    if resolved and root in resolved.parents and '.venv' not in resolved.parts:",
        "        found.add(resolved.relative_to(root).as_posix())",
        "print(json.dumps(sorted(found)))",
    ]
)


def test_every_repository_module_the_review_scope_check_loads_is_a_guarded_path() -> None:
    result = subprocess.run(
        [sys.executable, "-c", PROBE],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "PYTHONPATH": os.pathsep.join([str(REPO_ROOT), str(REPO_ROOT / "src")])},
    )
    loaded = json.loads(result.stdout)

    assert loaded and [file for file in loaded if not guarded_paths_touched([file])] == []
