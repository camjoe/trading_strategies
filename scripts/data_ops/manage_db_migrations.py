"""Operate the Alembic schema-migration lifecycle for the configured database.

Operator command (docs/numbered-database-migration-plan.md). Subcommands:

- ``status``    — database revision, repository head, and pending revisions.
- ``upgrade``   — apply revisions (default ``head``); creates a missing or
  empty database, and backs up an existing one first.
- ``downgrade`` — revert to an explicit target revision (or ``-1``); backs up first.
- ``baseline``  — validate an unversioned database against the ``0001`` schema
  with the shared comparator, then stamp it without replaying DDL.
- ``verify``    — compare the database against a temporary reference built at
  the same revision; detects manual drift even when ``alembic_version`` says
  the database is current.
- ``history``   — display the ordered revision chain.

Run::

    python -m scripts.data_ops.manage_db_migrations <command>
"""

from __future__ import annotations

import argparse
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from infrastructure.database import migration_runner
from infrastructure.database.backend import SQLiteBackend, get_backend
from infrastructure.database.schema_compare import compare_schemas
from infrastructure.database.schema_version import read_database_revisions
from trading.interfaces.runtime.data_ops.admin import backup_database

_PREFIX = "[manage-db-migrations]"

# The one-time transition target for pre-Alembic databases: they were built by
# the probe system, whose end state revision 0001 reproduces.
_BASELINE_REVISION = "0001"


def _db_path() -> Path:
    backend = get_backend()
    if not isinstance(backend, SQLiteBackend):
        raise RuntimeError("This tool currently supports only SQLite backends.")
    return backend.db_path


def _application_table_count(conn: Any) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' "
        "AND name NOT LIKE 'sqlite_%' AND name != 'alembic_version'"
    ).fetchone()
    return int(row[0])


def _classify(conn: Any, head: str) -> tuple[str, tuple[str, ...]]:
    """Return (state, revisions): one of unversioned-empty, unversioned-populated,
    branched, behind, at-head, or unknown-revision."""
    revisions = read_database_revisions(conn)
    if not revisions:
        state = "unversioned-empty" if _application_table_count(conn) == 0 else "unversioned-populated"
        return state, revisions
    if len(revisions) > 1:
        return "branched", revisions
    chain = [info.revision for info in migration_runner.revision_chain()]
    if revisions[0] not in chain:
        return "unknown-revision", revisions
    return ("at-head" if revisions[0] == head else "behind"), revisions


_REMEDIATION = {
    "unversioned-empty": "Run 'python -m scripts.data_ops.manage_db_migrations upgrade' to create the schema.",
    "unversioned-populated": "Run 'python -m scripts.data_ops.manage_db_migrations baseline' to adopt it.",
    "branched": "The revision history is branched; restore from backup and investigate before migrating.",
    "unknown-revision": (
        "The database revision is not in this repository's chain - it was likely written by newer "
        "code. Update the repository (or restore from backup) before migrating."
    ),
    "behind": "Run 'python -m scripts.data_ops.manage_db_migrations upgrade' to reach head.",
}


def _cmd_status(_args: argparse.Namespace) -> int:
    path = _db_path()
    print(f"{_PREFIX} Database: {path}")
    head = migration_runner.repository_head()
    print(f"{_PREFIX} Repository head: {head}")
    if not path.exists():
        print(f"{_PREFIX} State: missing - {_REMEDIATION['unversioned-empty']}")
        return 1

    conn = sqlite3.connect(path)
    try:
        state, revisions = _classify(conn, head)
    finally:
        conn.close()

    revision_text = ", ".join(revisions) if revisions else "(none)"
    print(f"{_PREFIX} Database revision: {revision_text}")
    print(f"{_PREFIX} State: {state}")
    if state == "behind":
        chain = [info.revision for info in migration_runner.revision_chain()]
        pending = chain[chain.index(revisions[0]) + 1 :]
        print(f"{_PREFIX} Pending revisions: {', '.join(pending)}")
    if state != "at-head":
        print(f"{_PREFIX} {_REMEDIATION[state]}")
    return 0 if state == "at-head" else 1


def _require_migratable(conn: Any, head: str, command: str) -> tuple[str, ...] | None:
    """Return the database's revisions when *command* may proceed, else None."""
    state, revisions = _classify(conn, head)
    if state in ("at-head", "behind"):
        return revisions
    print(f"{_PREFIX} Refusing {command}: database state is '{state}'. {_REMEDIATION[state]}")
    return None


def _cmd_upgrade(args: argparse.Namespace) -> int:
    path = _db_path()
    print(f"{_PREFIX} Database: {path}")
    head = migration_runner.repository_head()
    target = str(args.revision)
    conn = sqlite3.connect(path)
    try:
        state, revisions = _classify(conn, head)
        if state == "unversioned-empty":
            # Fresh setup: create the schema in place. No backup — there is
            # nothing to lose, and no application data is seeded.
            migration_runner.upgrade(target, connection=conn)
            print(f"{_PREFIX} Created schema at revision {', '.join(read_database_revisions(conn))}.")
            return 0
        if state not in ("at-head", "behind"):
            print(f"{_PREFIX} Refusing upgrade: database state is '{state}'. {_REMEDIATION[state]}")
            return 1
        resolved_target = head if target == "head" else target
        if revisions == (resolved_target,):
            print(f"{_PREFIX} Already at revision {resolved_target}; nothing to do.")
            return 0
        backup_path = backup_database()
        print(f"{_PREFIX} Backup created: {backup_path}")
        migration_runner.upgrade(target, connection=conn)
        print(f"{_PREFIX} Upgraded to revision {', '.join(read_database_revisions(conn))}.")
        return 0
    finally:
        conn.close()


def _cmd_downgrade(args: argparse.Namespace) -> int:
    path = _db_path()
    if not path.exists():
        print(f"{_PREFIX} Refusing downgrade: database is missing.")
        return 1
    head = migration_runner.repository_head()
    conn = sqlite3.connect(path)
    try:
        revisions = _require_migratable(conn, head, "downgrade")
        if revisions is None:
            return 1
        backup_path = backup_database()
        print(f"{_PREFIX} Backup created: {backup_path}")
        migration_runner.downgrade(str(args.revision), connection=conn)
        remaining = read_database_revisions(conn)
        revision_text = ", ".join(remaining) if remaining else "(base)"
        print(f"{_PREFIX} Downgraded to revision {revision_text}.")
        print(f"{_PREFIX} Downgrades restore schema shape only; restore the backup to recover data.")
        return 0
    finally:
        conn.close()


def _cmd_baseline(_args: argparse.Namespace) -> int:
    path = _db_path()
    if not path.exists():
        print(f"{_PREFIX} Refusing baseline: database is missing. {_REMEDIATION['unversioned-empty']}")
        return 1
    head = migration_runner.repository_head()
    conn = sqlite3.connect(path)
    try:
        state, _revisions = _classify(conn, head)
        if state != "unversioned-populated":
            print(f"{_PREFIX} Refusing baseline: database state is '{state}'. {_REMEDIATION.get(state, '')}")
            return 1

        reference = migration_runner.build_reference_connection(_BASELINE_REVISION)
        try:
            comparison = compare_schemas(reference, conn)
        finally:
            reference.close()
        if not comparison.matches:
            print(
                f"{_PREFIX} Baseline validation FAILED - the database does not match the "
                f"revision {_BASELINE_REVISION} schema. No revision was stamped."
            )
            for difference in comparison.differences:
                print(f"{_PREFIX}   {difference}")
            return 1

        migration_runner.stamp(_BASELINE_REVISION, connection=conn)
        print(f"{_PREFIX} Database matches revision {_BASELINE_REVISION}; stamped without replaying DDL.")
        if _BASELINE_REVISION != head:
            print(f"{_PREFIX} Repository head is {head}. {_REMEDIATION['behind']}")
        return 0
    finally:
        conn.close()


def _cmd_verify(_args: argparse.Namespace) -> int:
    path = _db_path()
    if not path.exists():
        print(f"{_PREFIX} Refusing verify: database is missing.")
        return 1
    head = migration_runner.repository_head()
    conn = sqlite3.connect(path)
    try:
        state, revisions = _classify(conn, head)
        if state not in ("at-head", "behind"):
            print(f"{_PREFIX} Refusing verify: database state is '{state}'. {_REMEDIATION.get(state, '')}")
            return 1

        reference = migration_runner.build_reference_connection(revisions[0])
        try:
            comparison = compare_schemas(reference, conn)
        finally:
            reference.close()
        if not comparison.matches:
            print(f"{_PREFIX} Verify FAILED - schema drift against revision {revisions[0]}:")
            for difference in comparison.differences:
                print(f"{_PREFIX}   {difference}")
            return 1

        print(f"{_PREFIX} Schema matches revision {revisions[0]}.")
        if state == "behind":
            print(f"{_PREFIX} Note: database is behind head ({head}). {_REMEDIATION['behind']}")
        return 0
    finally:
        conn.close()


def _cmd_history(_args: argparse.Namespace) -> int:
    path = _db_path()
    current: tuple[str, ...] = ()
    if path.exists():
        conn = sqlite3.connect(path)
        try:
            current = read_database_revisions(conn)
        finally:
            conn.close()
    for info in migration_runner.revision_chain():
        marker = "  (current)" if info.revision in current else ""
        parent = info.down_revision or "base"
        print(f"{_PREFIX} {parent} -> {info.revision}: {info.message}{marker}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage Alembic schema migrations for the configured trading database.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_status = sub.add_parser("status", help="Show database revision, repository head, and pending revisions.")
    p_status.set_defaults(handler=_cmd_status)

    p_upgrade = sub.add_parser("upgrade", help="Apply revisions up to the target (default: head). Backs up first.")
    p_upgrade.add_argument("revision", nargs="?", default="head", help="Target revision (default: head).")
    p_upgrade.set_defaults(handler=_cmd_upgrade)

    p_downgrade = sub.add_parser("downgrade", help="Revert to an explicit target revision. Backs up first.")
    p_downgrade.add_argument("revision", help="Target revision, or -1 for one step down.")
    p_downgrade.set_defaults(handler=_cmd_downgrade)

    p_baseline = sub.add_parser(
        "baseline",
        help="Validate an unversioned database against the 0001 schema, then stamp it without running DDL.",
    )
    p_baseline.set_defaults(handler=_cmd_baseline)

    p_verify = sub.add_parser("verify", help="Compare the database schema against a reference at its revision.")
    p_verify.set_defaults(handler=_cmd_verify)

    p_history = sub.add_parser("history", help="Display the ordered revision chain.")
    p_history.set_defaults(handler=_cmd_history)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    handler = cast(Callable[[argparse.Namespace], int], args.handler)
    return handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
