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
