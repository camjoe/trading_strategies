"""Resolve a catalog strategy row into its runnable form.

The catalog-canonical read path: a book's assignment names a
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

from trading.domain.strategies.contracts import PrimitiveSpec
from trading.domain.strategies.parameter_validation import resolve_primitive
from trading.domain.strategies.resolution import resolve_strategy
from trading.models.strategy import StrategyRecord
from trading.repositories.book_bridge import strategy_id_for_label
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


def resolve_or_draft_strategy_record(
    conn: sqlite3.Connection,
    label: str | None,
    *,
    now_iso: str,
) -> StrategyRecord | None:
    """Resolve a strategy label to its catalog row, drafting one if it has none.

    The optimizer targets a strategy by name before that name necessarily has a
    catalog row — searching a primitive's parameter space is how a row earns its
    knobs. So an unknown label is created as a draft rather than rejected, which
    is what separates this from :func:`resolve_catalog_strategy`.

    Returns ``None`` only when ``label`` is empty.
    """
    strategy_id = strategy_id_for_label(conn, label, now_iso=now_iso)
    if strategy_id is None:
        return None
    return StrategyRepository(conn).fetch_by_id(strategy_id=strategy_id)
