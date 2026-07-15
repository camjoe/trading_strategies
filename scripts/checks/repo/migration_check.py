"""Migration chain integrity check.

Statically validates the Alembic revision directory
(``src/infrastructure/database/alembic/versions``) without importing Alembic:

1. Every revision file parses and declares string ``revision`` /
   ``down_revision`` (``None`` for the base) module attributes.
2. Revision ids are 4-digit numeric and unique.
3. The chain is linear: exactly one base, one head, no cycles or branches.
4. Numeric order matches chain order (each revision is greater than its parent).
5. Every revision defines non-empty ``upgrade()`` and ``downgrade()`` bodies.
6. Revision files are self-contained: no application imports.
7. ``schema_version.EXPECTED_HEAD_REVISION`` equals the directory head.

Run standalone::

    python -m scripts.checks.repo.migration_check
"""

from __future__ import annotations

import argparse
import ast
import re
from dataclasses import dataclass
from pathlib import Path

from common.paths.repo_paths import get_repo_root
from infrastructure.database.schema_version import EXPECTED_HEAD_REVISION

VERSIONS_DIR_REL = "src/infrastructure/database/alembic/versions"

# Revision files must stay self-contained (docs/numbered-database-migration-plan.md):
# no imports from application code, only alembic/sqlalchemy/stdlib.
FORBIDDEN_IMPORT_PREFIXES = (
    "infrastructure",
    "trading",
    "common",
    "paper_trading_web",
    "trends",
    "apps",
    "scripts",
    "tests",
)

NUMERIC_REVISION_RE = re.compile(r"^\d{4}$")


@dataclass(frozen=True)
class RevisionFile:
    path: Path
    revision: str | None
    down_revision: str | None
    has_down_revision: bool
    nonempty_upgrade: bool
    nonempty_downgrade: bool
    forbidden_imports: tuple[str, ...]


def _module_constant(tree: ast.Module, name: str) -> tuple[bool, str | None]:
    """Return (assigned, value) for a module-level string-or-None constant."""
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if name in targets and isinstance(node.value, ast.Constant):
                value = node.value.value
                return True, value if isinstance(value, str) else None
    return False, None


def _has_nonempty_function(tree: ast.Module, name: str) -> bool:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            body = list(node.body)
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                body = body[1:]  # drop the docstring
            return any(not isinstance(statement, ast.Pass) for statement in body)
    return False


def _forbidden_imports(tree: ast.Module) -> tuple[str, ...]:
    found: list[str] = []
    for node in ast.walk(tree):
        modules: list[str] = []
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules = [node.module]
        for module in modules:
            top = module.split(".", 1)[0]
            if top in FORBIDDEN_IMPORT_PREFIXES:
                found.append(module)
    return tuple(found)


def _parse_revision_file(path: Path) -> RevisionFile | None:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except OSError, SyntaxError:
        return None
    _, revision = _module_constant(tree, "revision")
    has_down, down_revision = _module_constant(tree, "down_revision")
    return RevisionFile(
        path=path,
        revision=revision,
        down_revision=down_revision,
        has_down_revision=has_down,
        nonempty_upgrade=_has_nonempty_function(tree, "upgrade"),
        nonempty_downgrade=_has_nonempty_function(tree, "downgrade"),
        forbidden_imports=_forbidden_imports(tree),
    )


def _chain_findings(files: list[RevisionFile]) -> list[str]:
    findings: list[str] = []
    by_revision: dict[str, RevisionFile] = {}
    for info in files:
        rel = info.path.name
        if info.revision is None:
            findings.append(f"{rel}: missing or non-string `revision` attribute")
            continue
        if not info.has_down_revision:
            findings.append(f"{rel}: missing `down_revision` attribute")
        if not NUMERIC_REVISION_RE.match(info.revision):
            findings.append(f"{rel}: revision id {info.revision!r} is not 4-digit numeric")
        if info.revision in by_revision:
            findings.append(f"{rel}: duplicate revision id {info.revision!r}")
            continue
        by_revision[info.revision] = info
        if not info.nonempty_upgrade:
            findings.append(f"{rel}: upgrade() is missing or empty")
        if not info.nonempty_downgrade:
            findings.append(f"{rel}: downgrade() is missing or empty")
        for module in info.forbidden_imports:
            findings.append(f"{rel}: forbidden application import '{module}' (revisions must be self-contained)")

    if findings:
        return findings

    bases = [info for info in by_revision.values() if info.down_revision is None]
    if len(bases) != 1:
        findings.append(f"expected exactly one base revision (down_revision = None), found {len(bases)}")
        return findings

    # Walk base -> head following the single child of each revision.
    children: dict[str, list[RevisionFile]] = {}
    for info in by_revision.values():
        if info.down_revision is not None:
            if info.down_revision not in by_revision:
                findings.append(f"{info.path.name}: down_revision {info.down_revision!r} does not exist")
                return findings
            children.setdefault(info.down_revision, []).append(info)

    current = bases[0]
    visited = {current.revision}
    while True:
        assert current.revision is not None
        successors = children.get(current.revision, [])
        if len(successors) > 1:
            names = ", ".join(sorted(s.path.name for s in successors))
            findings.append(f"revision {current.revision} has multiple children ({names}); the chain must be linear")
            return findings
        if not successors:
            break
        nxt = successors[0]
        assert nxt.revision is not None and current.revision is not None
        if int(nxt.revision) <= int(current.revision):
            findings.append(
                f"{nxt.path.name}: revision {nxt.revision} is not numerically greater "
                f"than its parent {current.revision}"
            )
        current = nxt
        visited.add(current.revision)

    unreachable = set(by_revision) - visited
    if unreachable:
        findings.append(f"revisions not reachable from the base: {', '.join(sorted(unreachable))}")

    head = current.revision
    if head != EXPECTED_HEAD_REVISION:
        findings.append(
            f"schema_version.EXPECTED_HEAD_REVISION is {EXPECTED_HEAD_REVISION!r} but the migration "
            f"directory head is {head!r}; update the constant in the same commit as the new revision"
        )
    return findings


def run_migration_check(repo_root: Path, *, quiet: bool = True, enforce: bool = True) -> int:
    """Validate the migration chain. Returns 0 when clean (or advisory), 1 otherwise."""
    versions_dir = repo_root / VERSIONS_DIR_REL
    findings: list[str] = []

    if not versions_dir.is_dir():
        findings.append(f"missing migration directory: {VERSIONS_DIR_REL}")
    else:
        files: list[RevisionFile] = []
        for path in sorted(versions_dir.glob("*.py")):
            if path.name == "__init__.py":
                continue
            parsed = _parse_revision_file(path)
            if parsed is None:
                findings.append(f"{path.name}: unreadable or syntactically invalid")
                continue
            files.append(parsed)
        if not files and not findings:
            findings.append(f"no revision files found in {VERSIONS_DIR_REL}")
        if not findings:
            findings.extend(_chain_findings(files))

    if not findings:
        if not quiet:
            print("Migration chain check: no problems found.")
        print("PASS: migration chain - linear numeric history matches the expected head.")
        return 0

    print(f"Migration chain check found {len(findings)} problem(s):")
    for finding in findings:
        print(f"  - {finding}")
    if not enforce:
        print("WARN: migration chain check found advisory issues.")
        return 0
    print("FAIL: migration chain check failed in enforce mode.")
    return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate the Alembic migration chain and head constant.")
    parser.add_argument("--repo-root", default=None, help="Repository root. Defaults to detected workspace root.")
    parser.add_argument("--advisory", action="store_true", help="Report findings without failing.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve() if args.repo_root else get_repo_root(__file__)
    return run_migration_check(repo_root=repo_root, enforce=not args.advisory, quiet=False)


if __name__ == "__main__":
    raise SystemExit(main())
