from __future__ import annotations

import hashlib
import json
import logging
import os
import pickle
import time
from pathlib import Path

import pandas as pd

from common.paths.repo_paths import get_repo_root

_REPO_ROOT = get_repo_root(__file__)
_DEFAULT_MARKET_DATA_CACHE_DIR = _REPO_ROOT / "local" / "cache" / "market_data"
_MARKET_DATA_CACHE_TTL_SECONDS = 24 * 60 * 60
_MARKET_DATA_CACHE_DIR_ENV = "TRADING_MARKET_DATA_CACHE_DIR"
_MARKET_DATA_CACHE_DISABLED_ENV = "TRADING_MARKET_DATA_CACHE_DISABLED"
_CACHE_MISS = object()

logger = logging.getLogger(__name__)


def market_data_cache_disabled() -> bool:
    raw = str(os.getenv(_MARKET_DATA_CACHE_DISABLED_ENV, "")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def market_data_cache_dir() -> Path:
    raw = str(os.getenv(_MARKET_DATA_CACHE_DIR_ENV, "")).strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return _DEFAULT_MARKET_DATA_CACHE_DIR


def market_data_cache_key(kind: str, **parts: object) -> str:
    payload = json.dumps(
        {
            "kind": kind,
            "parts": parts,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def market_data_cache_path(cache_key: str) -> Path:
    return market_data_cache_dir() / f"{cache_key}.pkl"


# What a cache entry is allowed to hold. Bar history is a dict of per-ticker
# frames, so a frame/series-only guard silently turned every bar-history read
# into a miss — the entry was written, rejected on read, and re-downloaded every
# time. The check is a sanity guard against a corrupt or foreign pickle, not a
# schema: widen it whenever a provider starts caching a new shape.
_CACHEABLE_TYPES = (pd.DataFrame, pd.Series, dict)


def read_market_data_cache(cache_key: str) -> pd.DataFrame | pd.Series | dict | object:
    if market_data_cache_disabled():
        return _CACHE_MISS

    cache_path = market_data_cache_path(cache_key)
    if not cache_path.exists():
        return _CACHE_MISS

    cache_age_seconds = os.path.getmtime(cache_path)
    if (time.time() - cache_age_seconds) > _MARKET_DATA_CACHE_TTL_SECONDS:
        return _CACHE_MISS

    try:
        with cache_path.open("rb") as handle:
            cached = pickle.load(handle)
    except OSError, pickle.UnpicklingError, EOFError:
        return _CACHE_MISS

    if not isinstance(cached, _CACHEABLE_TYPES):
        return _CACHE_MISS
    return cached


def write_market_data_cache(cache_key: str, value: pd.DataFrame | pd.Series | dict) -> None:
    if market_data_cache_disabled():
        return

    cache_dir = market_data_cache_dir()
    cache_path = market_data_cache_path(cache_key)
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        with cache_path.open("wb") as handle:
            pickle.dump(value, handle)
    except OSError as exc:
        logger.warning("Skipping market data cache write for %s: %s", cache_path, exc)
