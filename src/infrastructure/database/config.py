"""Which database file the process talks to."""

from __future__ import annotations

import os
from pathlib import Path

from common.paths import PAPER_TRADING_DB_PATH

_DEFAULT_DB_PATH = PAPER_TRADING_DB_PATH


def get_db_path() -> Path:
    """Return ``TRADING_DB_PATH`` if set, else the repo default.

    The sandbox and demo launchers set the env var to run against a disposable
    database.
    """
    env_path = os.getenv("TRADING_DB_PATH", "").strip()
    if env_path:
        return Path(env_path).expanduser().resolve()
    return _DEFAULT_DB_PATH
