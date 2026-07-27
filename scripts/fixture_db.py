"""Build and publish generated fixture databases under local/.

Two shapes are supported:

``build_fixture_database``
    Migrate and seed a fresh database, publishing it only after the whole build
    succeeds. Used by the demo, which wants a fresh story on every launch.

``checkout_sandbox``
    Restore a throwaway working copy from a cached *golden* build, rebuilding
    the golden only when the schema head or the seeder source has changed. Used
    by the sandbox, where the point is that the bed is identical every time and
    nothing written to it survives the next launch.

The golden cache is not a speed optimization — seeding takes about a second.
It exists so the bed is *stable*: a profile anchors its story to the day it is
built, so rebuilding on every launch would silently shift every date in the
database out from under whatever is being tested.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
from pathlib import Path

from infrastructure.database.migration_runner import upgrade
from infrastructure.database.schema_version import EXPECTED_HEAD_REVISION
from infrastructure.market_data.demo_provider import DemoMarketDataProvider
from trading.repositories import fixture_seed as fixture_seed_module
from trading.services.fixtures import (
    FixtureProfile,
    profiles as profiles_module,
    seed_fixture_database,
    seeding as seeding_module,
)

SQLITE_SIDECAR_SUFFIXES = ("", "-shm", "-wal", "-journal")

# Seeder modules that participate in the golden fingerprint: a change to any of
# them means a cached golden database no longer reflects the seeder. Resolved
# through the imported modules so the fingerprint does not depend on cwd.
_FINGERPRINT_MODULES = (profiles_module, seeding_module, fixture_seed_module)


def exact_local_targets(local_dir: Path, database_name: str) -> tuple[Path, ...]:
    """Return only the named SQLite file and its recognized sidecars under local/."""
    resolved_local = local_dir.resolve()
    database = (resolved_local / database_name).resolve()
    if database.parent != resolved_local or database.name != database_name:
        raise ValueError("Fixture database target must be an exact filename directly under local/.")
    return tuple(Path(f"{database}{suffix}") for suffix in SQLITE_SIDECAR_SUFFIXES)


def remove_exact_targets(local_dir: Path, database_name: str) -> None:
    for target in exact_local_targets(local_dir, database_name):
        target.unlink(missing_ok=True)


def build_fixture_database(
    repo_root: Path,
    *,
    profile: FixtureProfile,
    database_name: str,
    preparing_name: str,
) -> Path:
    """Migrate and seed a temporary database, publishing it only after success."""
    local_dir = (repo_root / "local").resolve()
    local_dir.mkdir(parents=True, exist_ok=True)
    final_path = exact_local_targets(local_dir, database_name)[0]
    preparing_path = exact_local_targets(local_dir, preparing_name)[0]
    remove_exact_targets(local_dir, preparing_name)
    try:
        conn = sqlite3.connect(preparing_path)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            upgrade(connection=conn)
            seed_fixture_database(conn, profile=profile, provider=DemoMarketDataProvider())
        finally:
            conn.close()
        remove_exact_targets(local_dir, database_name)
        os.replace(preparing_path, final_path)
    except BaseException:
        remove_exact_targets(local_dir, preparing_name)
        raise
    return final_path


def golden_fingerprint(*, profile: FixtureProfile) -> str:
    """Identify the build inputs: schema head, profile name, and seeder source."""
    digest = hashlib.sha256()
    digest.update(EXPECTED_HEAD_REVISION.encode("utf-8"))
    digest.update(profile.name.encode("utf-8"))
    for module in _FINGERPRINT_MODULES:
        source = module.__file__
        if source is None:
            raise RuntimeError(f"Cannot fingerprint {module.__name__}: it has no source file.")
        digest.update(Path(source).read_bytes())
    return digest.hexdigest()


def checkout_sandbox(
    repo_root: Path,
    *,
    profile: FixtureProfile,
    golden_name: str,
    working_name: str,
    force_rebuild: bool = False,
) -> tuple[Path, bool]:
    """Restore a throwaway working copy from the golden build.

    Returns the working-copy path and whether the golden was rebuilt. Anything
    written to the previous working copy is discarded — that is the point.
    """
    local_dir = (repo_root / "local").resolve()
    local_dir.mkdir(parents=True, exist_ok=True)
    golden_path = exact_local_targets(local_dir, golden_name)[0]
    working_path = exact_local_targets(local_dir, working_name)[0]
    stamp_path = golden_path.with_suffix(".fingerprint")

    fingerprint = golden_fingerprint(profile=profile)
    cached = stamp_path.read_text(encoding="utf-8").strip() if stamp_path.exists() else ""
    rebuilt = False
    if force_rebuild or not golden_path.exists() or cached != fingerprint:
        build_fixture_database(
            repo_root,
            profile=profile,
            database_name=golden_name,
            preparing_name=f"{Path(golden_name).stem}.preparing.db",
        )
        stamp_path.write_text(fingerprint, encoding="utf-8")
        rebuilt = True

    # Replace the working copy wholesale so no prior run's writes survive.
    remove_exact_targets(local_dir, working_name)
    shutil.copyfile(golden_path, working_path)
    return working_path, rebuilt
