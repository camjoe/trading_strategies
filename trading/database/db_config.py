from __future__ import annotations

import json
import os
from pathlib import Path
from common.project_paths import DB_CONFIG_PATH, PAPER_TRADING_DB_PATH, REPO_ROOT

_DEFAULT_DB_PATH = PAPER_TRADING_DB_PATH
_DEFAULT_CONFIG_PATH = DB_CONFIG_PATH


def _config_path() -> Path:
    raw = os.getenv("TRADING_DB_CONFIG")
    if raw:
        return Path(raw).expanduser().resolve()
    return _DEFAULT_CONFIG_PATH


def _path_from_file(config_path: Path) -> Path | None:
    if not config_path.exists():
        return None

    payload = json.loads(config_path.read_text(encoding="utf-8"))
    db_path_raw = str(payload.get("db_path", "")).strip()
    if not db_path_raw:
        return None

    candidate = Path(db_path_raw).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    return (REPO_ROOT / candidate).resolve()


def get_db_path() -> Path:
    """Resolve the active DB path from env/config with sensible fallback.

    Precedence:
    1) TRADING_DB_PATH env var
    2) db_path value from config file (local/db_config.json by default)
    3) default local/paper_trading.db
    """
    env_path = str(os.getenv("TRADING_DB_PATH", "")).strip()
    if env_path:
        return Path(env_path).expanduser().resolve()

    file_path = _path_from_file(_config_path())
    if file_path is not None:
        return file_path

    return _DEFAULT_DB_PATH
