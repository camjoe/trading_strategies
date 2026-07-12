"""Resolve a catalog strategy row into its runnable knobs.

The catalog-canonical read path (P6): a book's assignment names a
``strategies`` row, and this module turns that row into the effective signal
knobs — the primitive's code knob-schema defaults with the row's ``params_json``
layered on top. Making the catalog the source of the *knobs* is P6-1; the
signal-primitive resolution itself moves onto the row's ``primitive`` in P6-2.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any

from trading.domain.strategy_signals import resolve_primitive, resolve_strategy
from trading.repositories.strategies import StrategyRepository


class UnknownCatalogStrategyError(ValueError):
    """Raised when a strategy key has no ``strategies`` catalog row."""


@dataclass(frozen=True)
class ResolvedStrategy:
    """A catalog strategy resolved to its runnable form for a trading run."""

    strategy_key: str
    primitive: str
    params: dict[str, Any]


def resolve_catalog_strategy(conn: sqlite3.Connection, strategy_key: str) -> ResolvedStrategy:
    """Resolve a catalog strategy key to its primitive and effective knobs.

    The knobs are the primitive's code defaults with the row's ``params_json``
    layered over them, so a partial or stale ``params_json`` never drops a knob
    the signal function needs. Raises :class:`UnknownCatalogStrategyError` when
    no catalog row exists for the key.
    """
    key = strategy_key.strip().lower()
    record = StrategyRepository(conn).fetch_by_key(strategy_key=key)
    if record is None:
        raise UnknownCatalogStrategyError(f"No strategy catalog row for '{strategy_key}'.")
    params = {**_primitive_defaults(record.primitive, record.strategy_key), **_parse_params_json(record.params_json)}
    return ResolvedStrategy(strategy_key=record.strategy_key, primitive=record.primitive, params=params)


def resolve_catalog_params(conn: sqlite3.Connection, strategy_key: str) -> dict[str, Any]:
    """The effective signal knobs for a catalog strategy key (see ``resolve_catalog_strategy``)."""
    return resolve_catalog_strategy(conn, strategy_key).params


def _primitive_defaults(primitive: str, strategy_key: str) -> dict[str, Any]:
    """The code knob-schema defaults for a row's primitive.

    Transitional (P6-1): the label bridge mints draft rows whose ``primitive``
    is the raw assignment label, which can be a lenient alias rather than a
    canonical primitive id. When the primitive is not a canonical id, fall back
    to lenient registry resolution so knob defaults match the pre-catalog read
    path exactly. P6-2 makes ``primitive`` an authoritative canonical id and
    removes this fallback.
    """
    try:
        return dict(resolve_primitive(primitive).knob_schema)
    except ValueError:
        try:
            return dict(resolve_strategy(strategy_key).default_params)
        except ValueError:
            return {}


def _parse_params_json(params_json: str) -> dict[str, Any]:
    if not params_json or not params_json.strip():
        return {}
    data = json.loads(params_json)
    if not isinstance(data, dict):
        raise ValueError(f"strategies.params_json must be a JSON object, got {type(data).__name__}.")
    return dict(data)
