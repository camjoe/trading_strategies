"""Which database file the process talks to.

One override, one default. ``TRADING_DB_PATH`` is how the sandbox and demo
launchers (``scripts/launch_sandbox.py``, ``scripts/launch_demo.py``) point
tooling at a disposable database; everything else uses the repo default.

A ``local/db_config.json`` layer used to sit between the two. It was removed
because the env var already covers the "run against a temp database" case and
does it more safely: a config file persists across terminals, so a stale entry
silently redirects every later command — including ``manage_db_migrations
upgrade`` and ``delete-account`` — with nothing on screen to say so.
"""

from __future__ import annotations

import os
from pathlib import Path

from common.paths import PAPER_TRADING_DB_PATH

_DEFAULT_DB_PATH = PAPER_TRADING_DB_PATH


def get_db_path() -> Path:
    """Resolve the active DB path: ``TRADING_DB_PATH`` if set, else the repo default."""
    env_path = os.getenv("TRADING_DB_PATH", "").strip()
    if env_path:
        return Path(env_path).expanduser().resolve()
    return _DEFAULT_DB_PATH
