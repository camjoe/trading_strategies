import pytest

from scripts.forge.guarded_paths import guarded_paths_touched


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

    modules.add("__init__")
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
