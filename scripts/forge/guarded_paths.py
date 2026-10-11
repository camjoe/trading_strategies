"""Paths an unattended fixer must never change.

Broker, database, execution, and risk code comes from the review-scope rules that already mark them
high risk, so the two lists cannot drift apart. The rest are the pipeline's own controls, the checks and
configuration the gate runs, and the places that hold decisions or secrets. The tool-configuration names are a
partial list (vite, vitest, eslint, jest); other tools' configuration is not covered.
"""

import re
from collections.abc import Iterable
from pathlib import PurePosixPath

from scripts.checks.repo.review_scope_check import SCOPE_RULES

_EXTRA_GUARDS = (
    ("scripts/", "the forge tool, the gate's checks, and what the workflow imports"),
    ("src/common/__init__.py", "imported by the forge tool"),
    ("src/common/git.py", "the git helper the guards call"),
    ("src/__init__.py", "imported by the forge tool"),
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

_CODE_SUFFIX = r"(?:js|cjs|mjs|ts|cts|mts|json|yml|yaml)"
_EXECUTED_CONFIG = re.compile(
    rf"\.eslintrc|(?:(?:vite|vitest|eslint|jest)\.config|\.eslintrc)(?:\.[\w-]+)*\.{_CODE_SUFFIX}"
)

_SHORT_NAME = re.compile(r"~\d")

_RUN_ON_START = frozenset({"sitecustomize.py", "usercustomize.py"})

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


def _normalized(path: str) -> str:
    """*path* as Windows would resolve it: forward slashes, no case, no stream suffix, no trailing dots or spaces."""
    parts = path.replace("\\", "/").casefold().split("/")
    return "/".join(part if part in ("", ".", "..") else part.split(":", 1)[0].rstrip(" .") for part in parts)


def guarded_paths_touched(paths: Iterable[str]) -> list[str]:
    """One ``path: reason`` entry for each path in *paths* that falls under a guarded prefix or name.

    Matching ignores case, trailing dots and spaces, and ``:stream`` suffixes, because a Windows checkout treats
    ``Scripts/Forge``, ``scripts/forge.`` and ``scripts/forge::$DATA`` as the same file. A component that looks
    like an 8.3 short name (``VITE~1.TS``) is guarded too, since it can alias a guarded file.
    """
    guards = tuple((rule.prefix.casefold(), rule.reason) for rule in SCOPE_RULES if rule.high_risk) + tuple(
        (prefix.casefold(), reason) for prefix, reason in _EXTRA_GUARDS
    )
    executed_names = {name.casefold() for name in _EXECUTED_NAMES}
    found: list[str] = []
    for path in paths:
        normalized = _normalized(path)
        name = PurePosixPath(normalized).name
        reason = next((why for prefix, why in guards if normalized.startswith(prefix)), None)
        if reason is None and any(_SHORT_NAME.search(part) for part in normalized.split("/")):
            reason = "a name that may be a Windows short name for a guarded file"
        if reason is None and (name in _RUN_ON_START or name.endswith(".pth")):
            reason = "code Python runs when it starts"
        if reason is None and {".githooks", ".husky"} & set(normalized.split("/")[:-1]):
            reason = "commit hooks"
        if reason is None and name.startswith(".env"):
            reason = "credentials and environment"
        if reason is None and (name in executed_names or _EXECUTED_CONFIG.fullmatch(name)):
            reason = "code or scripts the gate or test runner executes"
        if reason:
            found.append(f"{path}: {reason}")
    return found
