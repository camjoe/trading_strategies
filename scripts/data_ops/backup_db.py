"""
Database backup script with retention management.

The live database now lives in local/paper_trading.db (gitignored).
Backups are written to a configurable directory (default: local/db_backups/).

Retention policy
----------------
- Keep the N most recent backups.
- Keep one permanent archive per calendar month (the oldest backup taken that
  month is never deleted regardless of the rolling-window limit).

Configuration
-------------
Edit the CONFIG block below to adjust paths and retention counts.
To store backups on an external drive or network share,
change BACKUP_DIR, e.g.:
    BACKUP_DIR = Path("D:/Backups/trading_db")
    BACKUP_DIR = Path.home() / "trading_db_backups"
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from common.repo_paths import get_repo_root

# ---------------------------------------------------------------------------
# CONFIG — edit this block to reconfigure without touching any logic below
# ---------------------------------------------------------------------------
REPO_ROOT = get_repo_root(__file__)

# Where backups are written.  Defaults to local/db_backups/ (gitignored).
BACKUP_DIR: Path = REPO_ROOT / "local" / "db_backups"

# Rolling window: how many recent copies to keep (monthly archives are on top of this).
KEEP_RECENT: int = 30
# ---------------------------------------------------------------------------

from trading.database.admin import backup_database  # noqa: E402


_STEM_PREFIX = "paper_trading_"
_STAMP_FMT = "%Y%m%d_%H%M%S"


def _parse_stamp(path: Path) -> datetime | None:
    """Extract the datetime embedded in a backup filename, or None if unparseable."""
    stem = path.stem
    if not stem.startswith(_STEM_PREFIX):
        return None
    raw = stem[len(_STEM_PREFIX):]
    try:
        return datetime.strptime(raw, _STAMP_FMT)
    except ValueError:
        return None


def _prune(directory: Path, keep_recent: int) -> list[Path]:
    """
    Remove old backups from *directory*, keeping:
      - The ``keep_recent`` most recent files.
      - The oldest backup in each calendar month (permanent monthly archive).

    Returns the list of deleted paths.
    """
    candidates = sorted(
        ((path, stamp) for path in directory.glob("*.db") if (stamp := _parse_stamp(path)) is not None),
        key=lambda item: item[1],
    )

    if len(candidates) <= keep_recent:
        return []

    # Oldest backup per YYYY-MM — these are never deleted.
    seen_months: dict[str, Path] = {}
    for path, stamp in candidates:
        month_key = stamp.strftime("%Y-%m")
        if month_key not in seen_months:
            seen_months[month_key] = path
    monthly_archives = set(seen_months.values())

    keep_set = {path for path, _stamp in candidates[-keep_recent:]} | monthly_archives
    deleted: list[Path] = []
    for path, _stamp in candidates:
        if path not in keep_set:
            path.unlink()
            deleted.append(path)

    return deleted


def _print_backup_summary(backup_path: object, deleted: list[Path]) -> None:
    print(f"[backup] Saved : {backup_path}")
    if not deleted:
        return
    print(f"[backup] Pruned {len(deleted)} old backup(s):")
    for path in deleted:
        print(f"           - {path.name}")


def run_backup(*, verbose: bool = True) -> dict[str, object]:
    """
    Create a timestamped backup and apply retention pruning.

    Returns a summary dict with the backup path and pruned files.
    """
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup_path = backup_database(destination=str(BACKUP_DIR))
    deleted = _prune(BACKUP_DIR, KEEP_RECENT)

    summary: dict[str, object] = {
        "backup": backup_path,
        "pruned": deleted,
    }

    if verbose:
        _print_backup_summary(backup_path, deleted)

    return summary


if __name__ == "__main__":
    run_backup()


