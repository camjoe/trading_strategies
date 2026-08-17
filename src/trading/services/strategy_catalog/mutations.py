"""Operator edit workflows for the strategy catalog.

The write side of making strategies data: create a tuned *variant* of a
code primitive, edit a draft strategy's knobs, or freeze a strategy so it stops
changing once it has evidence. Knob edits are validated against the primitive's
code schema, and only ``draft`` rows are mutable — tuning a frozen strategy
means creating a new variant (enforced by the repository guard).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from typing import Any

from common.json_columns import dumps_json_column, loads_json_object
from common.time import utc_now_iso
from trading.domain.exceptions import NotFoundError
from trading.domain.strategies.parameter_validation import resolve_primitive, validate_params_against_primitive
from trading.models.strategy import StrategyRecord
from trading.repositories.strategies import StrategyRepository


def create_strategy_variant(
    conn: sqlite3.Connection,
    *,
    strategy_key: str,
    primitive: str,
    params: Mapping[str, Any] | None = None,
    description: str | None = None,
    now_iso: str | None = None,
) -> StrategyRecord:
    """Create a new draft strategy row: a variant of ``primitive`` with tuned knobs.

    The knobs are validated against the primitive's code schema and stored as
    overrides (the read path layers them over the primitive defaults). Raises
    ``ValueError`` for an unknown primitive, invalid knobs, or a key already in
    the catalog.
    """
    now = now_iso or utc_now_iso()
    spec = resolve_primitive(primitive)
    validated = validate_params_against_primitive(spec.primitive, params or {})
    repo = StrategyRepository(conn)
    key = strategy_key.strip().lower()
    if not key:
        raise ValueError("strategy key cannot be empty.")
    if repo.fetch_by_key(strategy_key=key) is not None:
        raise ValueError(f"Strategy already exists: {key}")
    strategy_id = repo.insert(
        strategy_key=key,
        primitive=spec.primitive,
        params_json=dumps_json_column(validated),
        description=description,
        status="draft",
        enabled=1,
        created_at=now,
        updated_at=now,
    )
    return _fetch(repo, strategy_id)


def configure_strategy(
    conn: sqlite3.Connection,
    *,
    strategy_key: str,
    params: Mapping[str, Any] | None = None,
    enabled: bool | None = None,
    now_iso: str | None = None,
) -> StrategyRecord:
    """Edit a draft strategy's knobs and/or enabled flag.

    ``params`` are validated against the row's primitive and merged over the
    existing overrides (a partial edit keeps untouched knobs). Editing the knobs
    of a non-draft row raises ``StrategyImmutableError``; ``enabled`` may be
    toggled on any row. Raises ``NotFoundError`` for an unknown key.
    """
    now = now_iso or utc_now_iso()
    repo = StrategyRepository(conn)
    record = repo.fetch_by_key(strategy_key=strategy_key.strip().lower())
    if record is None:
        raise NotFoundError(f"Strategy not found: {strategy_key}")
    if params:
        validated = validate_params_against_primitive(record.primitive, params)
        existing = loads_json_object(record.params_json, where="strategies.params_json")
        merged = {**existing, **validated}
        repo.update_draft_knobs(
            strategy_id=record.id,
            primitive=record.primitive,
            params_json=dumps_json_column(merged),
            updated_at=now,
        )
    if enabled is not None:
        repo.set_enabled(strategy_id=record.id, enabled=int(bool(enabled)), updated_at=now)
    return _fetch(repo, record.id)


def freeze_strategy(
    conn: sqlite3.Connection,
    *,
    strategy_key: str,
    now_iso: str | None = None,
) -> StrategyRecord:
    """Freeze a draft strategy (one-way). A no-op on an already-frozen row."""
    now = now_iso or utc_now_iso()
    repo = StrategyRepository(conn)
    record = repo.fetch_by_key(strategy_key=strategy_key.strip().lower())
    if record is None:
        raise NotFoundError(f"Strategy not found: {strategy_key}")
    repo.freeze(strategy_id=record.id, updated_at=now)
    return _fetch(repo, record.id)


def _fetch(repo: StrategyRepository, strategy_id: int) -> StrategyRecord:
    record = repo.fetch_by_id(strategy_id=strategy_id)
    if record is None:
        raise RuntimeError(f"strategies row missing after write for strategy_id={strategy_id}")
    return record
