"""Where this repository's files live, and how to display a path relative to it.

Path *constants* resolved from the repository root, the folders that can move
out of the checkout through environment variables, and the one formatting
helper used when a path is logged, compared, or written into a report.

Locating the root itself is git's job — see :func:`common.git.get_repo_root`.
"""

from __future__ import annotations

import os
from pathlib import Path

from common.git import get_repo_root

# Canonical repository root resolved via git top-level discovery.
REPO_ROOT = get_repo_root(__file__)

# Common top-level directories reused across trading, UI, and scripts.
LOCAL_DIR = REPO_ROOT / "local"
TRADING_CONFIG_DIR = REPO_ROOT / "src" / "infrastructure" / "config"

# Canonical file locations used in multiple modules.
ACCOUNT_PROFILES_DIR = TRADING_CONFIG_DIR / "account_profiles"
DEFAULT_ACCOUNT_PROFILE_PATH = ACCOUNT_PROFILES_DIR / "default.json"
TRADE_UNIVERSES_DIR = TRADING_CONFIG_DIR / "trade_universes"
SYMBOL_SECTORS_PATH = TRADING_CONFIG_DIR / "symbol_sectors.json"
# Tracked template the operator copies to JOB_SCHEDULE_PATH and edits with real times.
JOB_SCHEDULE_EXAMPLE_PATH = TRADING_CONFIG_DIR / "job_schedule.example.json"
# The live desired schedule the scheduler CLI reads by default. Gitignored (real
# times are private), so it sits beside the tracked example, like .env / .env.example.
JOB_SCHEDULE_PATH = TRADING_CONFIG_DIR / "job_schedule.json"
PAPER_TRADING_DB_PATH = LOCAL_DIR / "paper_trading.db"
# Current registered-vs-desired schedule drift, written by manage_job_schedules and
# read by the web Admin panel. Overwritten each write — it is current state, not history.
SCHEDULE_STATUS_ARTIFACT_PATH = LOCAL_DIR / "artifacts" / "schedule_status.json"
LOGS_DIR = LOCAL_DIR / "logs"
EXPORTS_DIR = LOCAL_DIR / "exports"
SCREENSHOTS_DIR = LOCAL_DIR / "screenshots"

# Folder for data every checkout of this repository may share (database backups,
# the market-data cache, the review scorecard). Unset means this checkout's local/.
DATA_HOME_ENV = "TRADING_DATA_HOME"
# Overrides the database-backup folder alone, ahead of TRADING_DATA_HOME.
DB_BACKUPS_DIR_ENV = "TRADING_DB_BACKUPS_DIR"


def env_path(name: str) -> Path | None:
    """The path in environment variable *name*, expanded and absolute, or None when unset or blank."""
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    return Path(raw).expanduser().resolve()


def data_home() -> Path:
    """The shared data folder: ``$TRADING_DATA_HOME``, else this checkout's ``local/``."""
    return env_path(DATA_HOME_ENV) or LOCAL_DIR


def db_backups_dir() -> Path:
    """Where database backups go: ``$TRADING_DB_BACKUPS_DIR``, else ``db_backups/`` under :func:`data_home`."""
    return env_path(DB_BACKUPS_DIR_ENV) or data_home() / "db_backups"


def relative_posix(path: Path, root: Path) -> str:
    """Return *path* relative to *root* with POSIX separators."""
    return path.relative_to(root).as_posix()
