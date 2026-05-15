"""Sleeve universe configuration service.

Provides the service-layer entry point for assigning named trade universes to
individual sleeves.  Named universes are resolved at runtime via
:mod:`trading.services.universe_resolver`.
"""

from __future__ import annotations

import json
import sqlite3

from common.time import utc_now_iso
from trading.repositories.sleeves import update_sleeve_trade_universes
from trading.services.universe_resolver import list_available_universes


def configure_sleeve_trade_universes(
    conn: sqlite3.Connection,
    *,
    sleeve_id: int,
    names: list[str] | None,
) -> None:
    """Set the trade universe names for a sleeve.

    Args:
        conn: Database connection.
        sleeve_id: ID of the target sleeve.
        names: List of universe names (e.g. ``["large_cap", "growth"]``).
            Pass ``None`` or an empty list to clear the override (sleeve will
            fall back to the account-level or global universe).

    Raises:
        ValueError: If any name is not a recognised universe.
    """
    if not names:
        serialized: str | None = None
    else:
        available = set(list_available_universes())
        unknown = [n for n in names if n not in available]
        if unknown:
            raise ValueError(f"Unknown universe name(s): {unknown}. Available: {sorted(available) or '(none)'}")
        serialized = json.dumps(names, separators=(",", ":"))

    update_sleeve_trade_universes(
        conn,
        sleeve_id=sleeve_id,
        trade_universes=serialized,
        updated_at=utc_now_iso(),
    )
