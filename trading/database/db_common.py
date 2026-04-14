import json
from pathlib import Path
from typing import Any


def in_placeholders(values: tuple[object, ...] | list[object]) -> str:
    """Return comma-separated ``?`` placeholders for a SQL IN clause."""
    return ",".join(["?"] * len(values))

from common.tickers import load_tickers_from_file
from trading.database.db_config import get_db_path

# Type alias — the concrete type depends on the active DatabaseBackend.
DBConnection = Any

DB_PATH = get_db_path()

# Default source used to seed account-level overlay watchlists so regime overlays
# can evaluate a stable baseline universe even before the account accumulates holdings.
DEFAULT_ROTATION_OVERLAY_WATCHLIST_FILE = "trading/config/trade_universe.txt"

# Canonical seeded overlay watchlist shared by new-account defaults and account
# backfills when the watchlist column is introduced by migration.
DEFAULT_ROTATION_OVERLAY_WATCHLIST = load_tickers_from_file(
    str(Path(__file__).resolve().parents[2] / DEFAULT_ROTATION_OVERLAY_WATCHLIST_FILE)
)
DEFAULT_ROTATION_OVERLAY_WATCHLIST_JSON = json.dumps(
    DEFAULT_ROTATION_OVERLAY_WATCHLIST,
    separators=(",", ":"),
)
