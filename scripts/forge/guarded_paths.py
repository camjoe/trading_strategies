"""Paths an unattended fixer must never change.

Broker, database, execution, and risk code comes from the review-scope rules that already mark them
high risk, so the two lists cannot drift apart. The rest are the pipeline's own controls, the checks and
configuration the gate runs, and the places that hold decisions or secrets. The tool-configuration names are a
partial list (vite, vitest, eslint, jest); other tools' configuration is not covered.
"""

import posixpath
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
    ("docker/", "the container the gate and agents run in"),
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
    ("SECURITY.md", "the security policy"),
    ("local/", "private research and parameters"),
)

_CODE_SUFFIX = r"(?:js|cjs|mjs|ts|cts|mts|json|yml|yaml)"
_EXECUTED_CONFIG = re.compile(
    rf"\.eslintrc|(?:(?:vite|vitest|eslint|jest)\.config|\.eslintrc)(?:\.[\w-]+)*\.{_CODE_SUFFIX}"
)

_SHORT_NAME = re.compile(r"[^~/]{1,6}~\d{1,7}(?:\.[^./]{0,3})?")
_DRIVE = re.compile(r"^[a-z]:")

_RUN_ON_START = frozenset({"sitecustomize.py", "usercustomize.py"})

_AGENT_FILES = frozenset({"claude.md", "claude.local.md", "agents.md", ".mcp.json"})
_DIRECTORY_REASONS = {
    ".githooks": "commit hooks",
    ".husky": "commit hooks",
    ".claude": "agent permissions",
    ".vscode": "editor tasks that run commands",
    ".devcontainer": "container setup commands",
}

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


def _bare_name(component: str) -> str:
    """*component* without a ``:stream`` suffix and without the trailing dots and spaces Windows drops."""
    return component.split(":", 1)[0].rstrip(" .")


def _normalized(path: str) -> tuple[str, bool]:
    """*path* as Windows would resolve it, and whether it is not a path inside the repository.

    The first part has forward slashes, no case, no ``:stream`` suffix, no trailing dots or spaces, and ``.`` and
    ``..`` resolved. The second is true for an absolute path, one that climbs out of the repository, or one whose
    first component collapses to nothing and so turns into an absolute path.
    """
    slashed = path.replace("\\", "/").casefold()
    cleaned = "/".join(part if part in ("", ".", "..") else _bare_name(part) for part in slashed.split("/"))
    resolved = posixpath.normpath(cleaned)
    outside = (
        slashed.startswith("/")
        or cleaned.startswith("/")
        or bool(_DRIVE.match(slashed))
        or resolved == ".."
        or resolved.startswith("../")
    )
    return ("" if resolved == "." else resolved), outside


def _hides_a_directory_reference(path: str) -> bool:
    """Whether a component is only dots and spaces with a space in it, which Windows may read as ``..``."""
    parts = path.replace("\\", "/").split("/")
    return any(" " in part and not _bare_name(part) for part in parts)


def guarded_paths_touched(paths: Iterable[str]) -> list[str]:
    """One ``path: reason`` entry for each path in *paths* that falls under a guarded prefix or name.

    Paths are compared as Windows resolves them: ``Scripts/Forge``, ``scripts/forge.`` and
    ``scripts/forge::$DATA`` all name ``scripts/forge``, and ``.`` and ``..`` are resolved. A component shaped
    like an 8.3 short name (``VITE~1.TS``) is guarded. So is an absolute path, or one that leaves the repository.
    """
    guards = tuple((rule.prefix.casefold(), rule.reason) for rule in SCOPE_RULES if rule.high_risk) + tuple(
        (prefix.casefold(), reason) for prefix, reason in _EXTRA_GUARDS
    )
    executed_names = {name.casefold() for name in _EXECUTED_NAMES}
    found: list[str] = []
    for path in paths:
        normalized, outside = _normalized(path)
        name = PurePosixPath(normalized).name
        reason = "a path outside the repository, or not relative to it" if outside else None
        if reason is None:
            reason = next((why for prefix, why in guards if normalized.startswith(prefix)), None)
        if reason is None and _hides_a_directory_reference(path):
            reason = "a name made only of dots and spaces, which Windows may read as a directory reference"
        if reason is None and any(_SHORT_NAME.fullmatch(part) for part in normalized.split("/")):
            reason = "a name that may be a Windows short name for a guarded file"
        if reason is None and (name in _RUN_ON_START or name.endswith(".pth")):
            reason = "code Python runs when it starts"
        if reason is None:
            reason = next((why for part in normalized.split("/")[:-1] if (why := _DIRECTORY_REASONS.get(part))), None)
        if reason is None and name in _AGENT_FILES:
            reason = "instructions or tool servers an agent run loads"
        if reason is None and name.startswith(".env"):
            reason = "credentials and environment"
        if reason is None and (name in executed_names or _EXECUTED_CONFIG.fullmatch(name)):
            reason = "code or scripts the gate or test runner executes"
        if reason:
            found.append(f"{path}: {reason}")
    return found
