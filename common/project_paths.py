from __future__ import annotations

from common.repo_paths import get_repo_root

# Canonical repository root resolved via git top-level discovery.
REPO_ROOT = get_repo_root(__file__)

# Common top-level directories reused across trading, UI, and scripts.
LOCAL_DIR = REPO_ROOT / "local"
TRADING_DIR = REPO_ROOT / "trading"
TRADING_CONFIG_DIR = TRADING_DIR / "config"

# Canonical file locations used in multiple modules.
ACCOUNT_PROFILES_DIR = TRADING_CONFIG_DIR / "account_profiles"
LEGACY_ACCOUNT_PROFILES_DIR = TRADING_DIR / "account_profiles"
DEFAULT_ACCOUNT_PROFILE_PATH = ACCOUNT_PROFILES_DIR / "default.json"
TRADE_UNIVERSE_PATH = TRADING_CONFIG_DIR / "trade_universe.txt"
DB_CONFIG_PATH = LOCAL_DIR / "db_config.json"
PAPER_TRADING_DB_PATH = LOCAL_DIR / "paper_trading.db"
LOGS_DIR = LOCAL_DIR / "logs"
EXPORTS_DIR = LOCAL_DIR / "exports"
SCREENSHOTS_DIR = LOCAL_DIR / "screenshots"
TEST_INVESTMENTS_PATH = LOCAL_DIR / "test_investments.txt"
LEGACY_TEST_INVESTMENTS_PATH = LOCAL_DIR / "test_invesments.txt"

# Historical relative prefix still accepted for account profile file rewrites.
LEGACY_ACCOUNT_PROFILES_PREFIX = "trading/account_profiles/"
