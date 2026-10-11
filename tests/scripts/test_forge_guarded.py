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
