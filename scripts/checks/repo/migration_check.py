"""Migration head-constant check.

Fails when ``schema_version.EXPECTED_HEAD_REVISION`` does not match the single
head of the Alembic migration directory — the one desync PR review cannot
reliably catch (a new revision without the constant bump breaks every runtime
connection). Revision hygiene — linear numeric chain, nonempty
upgrade()/downgrade(), self-contained files — is PR-review discipline
(`.ai/skills/db-migration/`), and Alembic itself refuses branched histories.

Run standalone::

    python -m scripts.checks.repo.migration_check
"""

from __future__ import annotations

import argparse
from pathlib import Path

from common.paths.repo_paths import get_repo_root
from infrastructure.database import migration_runner
from infrastructure.database.schema_version import EXPECTED_HEAD_REVISION


def run_migration_check(repo_root: Path, *, quiet: bool = True, enforce: bool = True) -> int:
    """Check the expected-head constant against the migration directory."""
    del repo_root  # interface parity with the other repo checks; the chain resolves via import
    try:
        head = migration_runner.repository_head()
    except RuntimeError as exc:
        finding = str(exc)
    else:
        if head == EXPECTED_HEAD_REVISION:
            if not quiet:
                print(f"Migration head check: directory head {head} matches the expected constant.")
            print("PASS: migration head - EXPECTED_HEAD_REVISION matches the migration directory.")
            return 0
        finding = (
            f"schema_version.EXPECTED_HEAD_REVISION is {EXPECTED_HEAD_REVISION!r} but the migration "
            f"directory head is {head!r}; update the constant in the same commit as the new revision"
        )

    print(f"Migration head check found a problem:\n  - {finding}")
    if not enforce:
        print("WARN: migration head check found advisory issues.")
        return 0
    print("FAIL: migration head check failed in enforce mode.")
    return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check EXPECTED_HEAD_REVISION against the migration directory head.")
    parser.add_argument("--repo-root", default=None, help="Repository root. Defaults to detected workspace root.")
    parser.add_argument("--advisory", action="store_true", help="Report findings without failing.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve() if args.repo_root else get_repo_root(__file__)
    return run_migration_check(repo_root=repo_root, enforce=not args.advisory, quiet=False)


if __name__ == "__main__":
    raise SystemExit(main())
