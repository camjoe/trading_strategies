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
To store backups on an external drive, OneDrive, or network share,
change BACKUP_DIR, e.g.:
    BACKUP_DIR = Path("D:/Backups/trading_db")
    BACKUP_DIR = Path.home() / "OneDrive" / "trading_db_backups"
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# CONFIG — edit this block to reconfigure without touching any logic below
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent

# Where backups are written.  Defaults to local/db_backups/ (gitignored).
BACKUP_DIR: Path = _REPO_ROOT / "local" / "db_backups"

# Rolling window: how many recent copies to keep (monthly archives are on top of this).
KEEP_RECENT: int = 30
# ---------------------------------------------------------------------------

sys.path.insert(0, str(_REPO_ROOT))
from dev_tools.db_admin import backup_database  # noqa: E402


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
        (p for p in directory.glob("*.db") if _parse_stamp(p) is not None),
        key=lambda p: _parse_stamp(p),  # type: ignore[arg-type]
    )

    if len(candidates) <= keep_recent:
        return []

    # Oldest backup per YYYY-MM — these are never deleted.
    monthly_archives: set[Path] = set()
    seen_months: dict[str, Path] = {}
    for p in candidates:
        stamp = _parse_stamp(p)
        month_key = stamp.strftime("%Y-%m")  # type: ignore[union-attr]
        if month_key not in seen_months:
            seen_months[month_key] = p
    monthly_archives = set(seen_months.values())

    keep_set = set(candidates[-keep_recent:]) | monthly_archives
    deleted: list[Path] = []
    for p in candidates:
        if p not in keep_set:
            p.unlink()
            deleted.append(p)

    return deleted


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
        print(f"[backup] Saved : {backup_path}")
        if deleted:
            print(f"[backup] Pruned {len(deleted)} old backup(s):")
            for p in deleted:
                print(f"           - {p.name}")

    return summary


if __name__ == "__main__":
    run_backup()

