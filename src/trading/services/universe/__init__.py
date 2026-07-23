"""Universe service package — resolves named universe identifiers to ticker lists."""

from __future__ import annotations

from trading.services.universe.resolver import list_available_universes, resolve_named_universes

__all__ = [
    "list_available_universes",
    "resolve_named_universes",
]
