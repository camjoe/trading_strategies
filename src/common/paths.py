"""Where this repository's files live, and how to display a path relative to it.

Path *constants* resolved from the repository root, plus the one formatting
helper used when a path is logged, compared, or written into a report.

Locating the root itself is git's job — see :func:`common.git.get_repo_root`.
"""

from __future__ import annotations

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
PAPER_TRADING_DB_PATH = LOCAL_DIR / "paper_trading.db"
DB_BACKUPS_DIR = LOCAL_DIR / "db_backups"
LOGS_DIR = LOCAL_DIR / "logs"
EXPORTS_DIR = LOCAL_DIR / "exports"
SCREENSHOTS_DIR = LOCAL_DIR / "screenshots"


def relative_posix(path: Path, root: Path) -> str:
    """Return *path* relative to *root* with POSIX separators."""
    return path.relative_to(root).as_posix()
