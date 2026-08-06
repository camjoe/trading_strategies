"""On-disk transport cache for market-data fetches.

Keyed by a hash of the request arguments and expired by file mtime, so a repeated
fetch within the TTL costs no network request. Adapters own what they put in it;
this module has no knowledge of the shapes beyond the read-side type guard.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import pickle
import time
from pathlib import Path

import pandas as pd

from common.paths import REPO_ROOT

_DEFAULT_MARKET_DATA_CACHE_DIR = REPO_ROOT / "local" / "cache" / "market_data"
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


# What a cache entry is allowed to hold. A guard against a stale or foreign
# pickle, not a security boundary — pickle.load already ran arbitrary code by the
# time this is checked. Not a schema either: widen it whenever an adapter starts
# caching a new shape, or reads of that shape silently become permanent misses.
_CACHEABLE_TYPES = (pd.DataFrame, pd.Series, dict)


def read_market_data_cache(cache_key: str) -> pd.DataFrame | pd.Series | dict | object:
    if market_data_cache_disabled():
        return _CACHE_MISS

    cache_path = market_data_cache_path(cache_key)
    if not cache_path.exists():
        return _CACHE_MISS

    modified_at = os.path.getmtime(cache_path)
    if (time.time() - modified_at) > _MARKET_DATA_CACHE_TTL_SECONDS:
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
