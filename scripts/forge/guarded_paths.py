"""Paths an unattended fixer must never change.

Broker, database, execution, and risk code comes from the review-scope rules that already mark them
high risk, so the two lists cannot drift apart. The rest are the pipeline's own controls, the checks and
configuration the gate runs, and the places that hold decisions or secrets.
"""

from collections.abc import Iterable
from pathlib import PurePosixPath

from scripts.checks.repo.review_scope_check import SCOPE_RULES

_EXTRA_GUARDS = (
    ("scripts/forge/", "the forge tool and its checks"),
    ("scripts/checks/", "the gate's checks and the review-scope rules"),
    ("scripts/run_checks.py", "the gate"),
    ("scripts/fix_checks.py", "the gate"),
    ("src/common/git.py", "the git helper the guards call"),
    (".github/", "the pipeline's workflows and repository settings"),
    (".claude/", "agent permissions"),
    (".ai/skills/", "the skills"),
    ("AGENTS.md", "the standing authorizations"),
    ("CLAUDE.md", "the standing authorizations"),
    ("docs/adr/", "accepted decisions"),
    ("docs/architecture/", "the architecture rules"),
    ("pyproject.toml", "build and tool configuration"),
    ("pytest.ini", "build and tool configuration"),
    ("ruff.toml", "build and tool configuration"),
    ("requirements", "dependencies"),
    (".pre-commit", "commit hooks"),
    (".gitattributes", "repository settings"),
    (".gitmodules", "repository settings"),
    (".githooks/", "commit hooks"),
    (".husky/", "commit hooks"),
    ("SECURITY.md", "the security policy"),
    ("local/", "private research and parameters"),
)

_EXECUTED_CONFIGS = ("vite.config.", "vitest.config.", "eslint.config.", "jest.config.", ".eslintrc")

_EXECUTED_NAMES = frozenset(
    {
        "conftest.py",
        "package.json",
        "package-lock.json",
        "Makefile",
        "tox.ini",
        "setup.cfg",
        "setup.py",
        "noxfile.py",
        ".coveragerc",
        "mypy.ini",
        ".flake8",
    }
)


def guarded_paths_touched(paths: Iterable[str]) -> list[str]:
    """One ``path: reason`` entry for each path in *paths* that falls under a guarded prefix or name."""
    guards = tuple((rule.prefix, rule.reason) for rule in SCOPE_RULES if rule.high_risk) + _EXTRA_GUARDS
    found: list[str] = []
    for path in paths:
        normalized = path.replace("\\", "/")
        name = PurePosixPath(normalized).name
        reason = next((why for prefix, why in guards if normalized.startswith(prefix)), None)
        if reason is None and name.startswith(".env"):
            reason = "credentials and environment"
        if reason is None and (name in _EXECUTED_NAMES or name.startswith(_EXECUTED_CONFIGS)):
            reason = "code or scripts the gate or test runner executes"
        if reason:
            found.append(f"{path}: {reason}")
    return found
