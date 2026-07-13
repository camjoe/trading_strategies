"""Resolve a catalog strategy row into its runnable form.

The catalog-canonical read path (P6): a book's assignment names a
``strategies`` row, and this module turns that row into the code primitive that
produces signals plus the effective knobs to run it with. The knobs are the
primitive's code defaults with the row's ``params_json`` layered on top.

Resolution is keyed on the row's ``primitive`` column, so a data *variant* — a
new ``strategy_key`` bound to the same primitive with different knobs — runs the
right signal function. ``STRATEGY_REGISTRY`` is consulted only as an alias-compat
shim for legacy rows whose primitive column holds an alias rather than a
canonical id.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any

from trading.domain.strategy_signals import PrimitiveSpec, resolve_primitive, resolve_strategy
from trading.models.strategy.strategy_record import StrategyRecord
from trading.repositories.strategies import StrategyRepository


class UnknownCatalogStrategyError(ValueError):
    """Raised when a strategy has no catalog row or an unresolvable primitive."""


@dataclass(frozen=True)
class ResolvedStrategy:
    """A catalog strategy resolved to its runnable form for a trading run."""

    strategy_key: str
    primitive_spec: PrimitiveSpec
    params: dict[str, Any]

    @property
    def primitive(self) -> str:
        """The canonical code primitive id backing this strategy."""
        return self.primitive_spec.primitive


def resolve_catalog_strategy(conn: sqlite3.Connection, strategy_key: str) -> ResolvedStrategy:
    """Resolve a catalog strategy key to its code primitive and effective knobs.

    The knobs are the primitive's code defaults with the row's ``params_json``
    layered over them, so a partial or stale ``params_json`` never drops a knob
    the signal function needs. Raises :class:`UnknownCatalogStrategyError` when
    no catalog row exists for the key or its primitive does not resolve to code.
    """
    key = strategy_key.strip().lower()
    record = StrategyRepository(conn).fetch_by_key(strategy_key=key)
    if record is None:
        raise UnknownCatalogStrategyError(f"No strategy catalog row for '{strategy_key}'.")
    primitive_spec = _resolve_primitive_spec(record)
    params = {**dict(primitive_spec.knob_schema), **_parse_params_json(record.params_json)}
    return ResolvedStrategy(strategy_key=record.strategy_key, primitive_spec=primitive_spec, params=params)


def resolve_catalog_params(conn: sqlite3.Connection, strategy_key: str) -> dict[str, Any]:
    """The effective signal knobs for a catalog strategy key (see ``resolve_catalog_strategy``)."""
    return resolve_catalog_strategy(conn, strategy_key).params


def _resolve_primitive_spec(record: StrategyRecord) -> PrimitiveSpec:
    """Resolve a row's ``primitive`` column to its canonical code spec.

    A row's primitive is normally a canonical primitive id. Legacy rows minted
    by the label bridge can hold an alias (e.g. ``momentum``) instead; those
    resolve through the registry alias map — the one runtime use of
    ``STRATEGY_REGISTRY`` kept as an alias-compat shim.
    """
    try:
        return resolve_primitive(record.primitive)
    except ValueError:
        pass
    try:
        return resolve_primitive(resolve_strategy(record.primitive).strategy_id)
    except ValueError as exc:
        raise UnknownCatalogStrategyError(
            f"Strategy '{record.strategy_key}' primitive {record.primitive!r} does not resolve to a code primitive."
        ) from exc


def _parse_params_json(params_json: str) -> dict[str, Any]:
    if not params_json or not params_json.strip():
        return {}
    data = json.loads(params_json)
    if not isinstance(data, dict):
        raise ValueError(f"strategies.params_json must be a JSON object, got {type(data).__name__}.")
    return dict(data)
